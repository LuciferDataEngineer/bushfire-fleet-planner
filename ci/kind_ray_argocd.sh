#!/usr/bin/env bash
# Install KubeRay and Argo CD on the local kind cluster, sync k8s/ray from git, and wait
# until the slim RayJob prints RAYJOB_OK.
set -euo pipefail

SHA="${GITHUB_SHA:?}"
TOKEN="${GITHUB_TOKEN:?}"
REPO="${GITHUB_REPOSITORY:?}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

dump() {
  echo "----- debug dump -----"
  kubectl get pods -A || true
  kubectl get application -n argocd -o yaml || true
  kubectl get rayjob -n bushfire -o yaml || true
  echo "----- submitter logs -----"
  kubectl --request-timeout=20s logs -n bushfire job/fire-season-sim --tail=200 || true
  kubectl logs -n bushfire -l ray.io/node-type=head --tail=80 || true
  kubectl logs -n bushfire -l ray.io/node-type=worker --tail=40 || true
  kubectl logs -n kuberay -l app.kubernetes.io/name=kuberay-operator --tail=80 || true
}
trap dump ERR

helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

helm upgrade --install kuberay-operator kuberay/kuberay-operator \
  --version 1.2.2 \
  --namespace kuberay --create-namespace \
  --wait --timeout 8m

helm upgrade --install argocd argo/argo-cd \
  --version 7.7.16 \
  --namespace argocd --create-namespace \
  --values "$ROOT/ci/argocd-values.yaml" \
  --wait --timeout 12m

kubectl -n argocd delete secret bushfire-repo --ignore-not-found
kubectl -n argocd create secret generic bushfire-repo \
  --from-literal=url="https://github.com/${REPO}.git" \
  --from-literal=username=x-access-token \
  --from-literal=password="${TOKEN}"
kubectl -n argocd label secret bushfire-repo argocd.argoproj.io/secret-type=repository --overwrite

sed "s|targetRevision: main|targetRevision: ${SHA}|" "$ROOT/k8s/argocd/application.yaml" \
  | kubectl apply -f -

echo "waiting for Argo CD to sync ${SHA}"
for _ in $(seq 1 40); do
  status="$(kubectl get application bushfire-ray -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || true)"
  echo "sync=${status}"
  if [[ "${status}" == "Synced" ]]; then
    break
  fi
  sleep 15
done
if [[ "${status}" != "Synced" ]]; then
  echo "Argo CD did not reach Synced"
  exit 1
fi

# sim.py on the committed 8-region extract (seed 15, 12 seasons of 30 days, beta 0.8).
# Both means are severe days inside one season, and the hotter draw is above the uniform draw.
EXPECTED_LINE="RAYJOB_OK regions=8 mean_uniform=4.0625 mean_hotter=8.9688"

# Head pods only print the Ray runtime. Driver stdout is streamed by `ray job submit`
# into the submitter Kubernetes Job, which KubeRay names the same as the RayJob.
# `ray job logs` on the head is the fallback while that pod still exists.
driver_logs() {
  local logs="" head_pod="" job_id="" via_head=""
  logs="$(kubectl --request-timeout=30s logs -n bushfire job/fire-season-sim --tail=500 2>/dev/null || true)"
  if [[ -z "${logs//[$' \t\n']/}" ]]; then
    logs="$(kubectl --request-timeout=30s logs -n bushfire -l job-name=fire-season-sim --tail=500 2>/dev/null || true)"
  fi
  if [[ -z "${logs//[$' \t\n']/}" ]]; then
    logs="$(kubectl --request-timeout=30s logs -n bushfire -l batch.kubernetes.io/job-name=fire-season-sim --tail=500 2>/dev/null || true)"
  fi
  if ! grep -F "${EXPECTED_LINE}" <<<"${logs}" >/dev/null; then
    head_pod="$(kubectl --request-timeout=20s get pods -n bushfire -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    job_id="$(kubectl --request-timeout=20s get rayjob fire-season-sim -n bushfire -o jsonpath='{.status.jobId}' 2>/dev/null || true)"
    if [[ -n "${head_pod}" && -n "${job_id}" ]]; then
      via_head="$(timeout 40 kubectl --request-timeout=30s exec -n bushfire "${head_pod}" -- ray job logs "${job_id}" --address http://127.0.0.1:8265 2>/dev/null || true)"
      logs="${logs}"$'\n'"${via_head}"
    fi
  fi
  printf '%s\n' "${logs}"
}

echo "waiting for RayJob"
job_status=""
ray_deadline=$((SECONDS + 600))
while (( SECONDS < ray_deadline )); do
  job_status="$(kubectl --request-timeout=20s get rayjob fire-season-sim -n bushfire -o jsonpath='{.status.jobStatus}' 2>/dev/null || true)"
  echo "rayjob=${job_status:-pending}"
  if [[ "${job_status}" == "SUCCEEDED" || "${job_status}" == "FAILED" ]]; then
    break
  fi
  sleep 15
done

if [[ "${job_status}" != "SUCCEEDED" ]]; then
  echo "RayJob did not succeed: status=${job_status:-timeout} after 600s"
  echo "----- submitter logs -----"
  driver_logs || true
  exit 1
fi

logs=""
log_deadline=$((SECONDS + 120))
while (( SECONDS < log_deadline )); do
  logs="$(driver_logs)"
  if grep -F "${EXPECTED_LINE}" <<<"${logs}" >/dev/null; then
    break
  fi
  sleep 10
done

if ! grep -F "${EXPECTED_LINE}" <<<"${logs}" >/dev/null; then
  echo "RayJob did not succeed: driver output missing a sane sampler result"
  echo "expected: ${EXPECTED_LINE}"
  echo "----- submitter logs -----"
  printf '%s\n' "${logs}"
  exit 1
fi
echo "kind ray job succeeded: ${EXPECTED_LINE}"
trap - ERR
