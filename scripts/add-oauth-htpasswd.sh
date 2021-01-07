#!/usr/bin/env bash

KUBECONFIG=${1}
HTPASSWORD=${2}

OC="oc --kubeconfig ${KUBECONFIG}"

[[ -z ${HTPASSWORD} ]] && {
    echo "script need the kubeconfig and htpassword as arguments"
    exit 1
}

[[ -e ${HTPASSWORD} ]] || {
    echo "cannot find ${HTPASSWORD}"
    exit 1
}

function os4_add_htpasswd_auth() {
    ${OC} get secret htpasswd-secret -n openshift-config 2>/dev/null >/dev/null  && return || true

    ${OC} create secret generic htpasswd-secret \
       --from-file=htpasswd=${HTPASSWORD} -n openshift-config
    ${OC} patch oauth cluster -n openshift-config --type merge --patch "spec:
  identityProviders:
  - htpasswd:
      fileData:
        name: htpasswd-secret
    mappingMethod: claim
    name: htpasswd
    type: HTPasswd
"
    for user in $(awk -F: '{print $1}' ${HTPASSWORD});do
        ${OC} adm policy add-cluster-role-to-user cluster-admin ${user}
    done
}

os4_add_htpasswd_auth