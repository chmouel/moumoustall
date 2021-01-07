#!/usr/bin/env bash

set -e
export KUBECONFIG=${1}
[[ -z ${KUBECONFIG} ]] && { echo "need kubeconfig"; exit 1 ;}

oc patch scheduler cluster --type='merge' -p '{"spec":{"mastersSchedulable": true}}'
workermachine=$(oc get machinesets -n openshift-machine-api --no-headers -o name| sed 's/machineset.machine.openshift.io\///')
oc scale --replicas=0 machineset ${workermachine} -n openshift-machine-api
