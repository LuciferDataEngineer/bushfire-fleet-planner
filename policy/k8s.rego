package main

import rego.v1

container_list contains c if {
  c := input.spec.template.spec.containers[_]
}

container_list contains c if {
  c := input.spec.jobTemplate.spec.template.spec.containers[_]
}

container_list contains c if {
  c := input.spec.rayClusterSpec.headGroupSpec.template.spec.containers[_]
}

container_list contains c if {
  c := input.spec.rayClusterSpec.workerGroupSpecs[_].template.spec.containers[_]
}

container_list contains c if {
  c := input.spec.submitterPodTemplate.spec.containers[_]
}

name := object.get(input.metadata, "name", "?")

deny contains msg if {
  some c in container_list
  endswith(lower(c.image), ":latest")
  msg := sprintf("%s/%s container %s uses a latest tag (%s)", [input.kind, name, c.name, c.image])
}

deny contains msg if {
  some c in container_list
  not contains(c.image, ":")
  msg := sprintf("%s/%s container %s has no image tag", [input.kind, name, c.name])
}

deny contains msg if {
  some c in container_list
  not c.resources.limits.cpu
  msg := sprintf("%s/%s container %s is missing a cpu limit", [input.kind, name, c.name])
}

deny contains msg if {
  some c in container_list
  not c.resources.limits.memory
  msg := sprintf("%s/%s container %s is missing a memory limit", [input.kind, name, c.name])
}

deny contains msg if {
  some c in container_list
  c.securityContext.runAsNonRoot != true
  msg := sprintf("%s/%s container %s must set runAsNonRoot", [input.kind, name, c.name])
}
