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
  kubectl logs -n bushfire -l ray.io/node-type=head --tail=200 || true
  kubectl logs -n bushfire -l ray.io/node-type=worker --tail=80 || true
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

echo "waiting for RayJob"
job_status=""
for _ in $(seq 1 40); do
  job_status="$(kubectl get rayjob fire-season-sim -n bushfire -o jsonpath='{.status.jobStatus}' 2>/dev/null || true)"
  echo "rayjob=${job_status}"
  if [[ "${job_status}" == "SUCCEEDED" || "${job_status}" == "FAILED" ]]; then
    break
  fi
  sleep 15
done

logs="$(kubectl logs -n bushfire -l ray.io/node-type=head --tail=300 2>/dev/null || true)"
echo "${logs}"
if [[ "${job_status}" != "SUCCEEDED" ]] || ! grep -q "RAYJOB_OK" <<<"${logs}"; then
  echo "RayJob did not succeed"
  exit 1
fi
echo "kind ray job succeeded"
trap - ERR
