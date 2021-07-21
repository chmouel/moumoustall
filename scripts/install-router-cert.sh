#!/usr/bin/env bash

set -eu

CLUSTER_NAME=${1}

[[ -z ${CLUSTER_NAME} ]] && exit 1

export CERTDIR=./installs/${CLUSTER_NAME}/certificates
mkdir -p ${CERTDIR}

OC="oc --kubeconfig ./installs/${CLUSTER_NAME}/auth/kubeconfig"

export LE_API=$(${OC} whoami --show-server | cut -f 2 -d ':' | cut -f 3 -d '/' | sed 's/-api././')
export LE_WILDCARD=$(${OC} get ingresscontroller default -n openshift-ingress-operator -o jsonpath='{.status.domain}')
export LE_WORKING_DIR="${HOME}/.acme.sh"

function install_cert() {
	mkdir -p ${CERTDIR}
	$HOME/.acme.sh/acme.sh --issue -d ${LE_API} -d *.${LE_WILDCARD} --dns dns_aws
	${HOME}/.acme.sh/acme.sh --install-cert -d ${LE_API} -d *.${LE_WILDCARD} --cert-file ${CERTDIR}/cert.pem --key-file ${CERTDIR}/key.pem --fullchain-file ${CERTDIR}/fullchain.pem --ca-file ${CERTDIR}/ca.cer
}

function configure_router_certs() {
	${OC} --kubeconfig=$KUBECONFIG delete secret router-certs -n openshift-ingress 2>/dev/null || true; 
	
	${OC} get secret router-certs -n openshift-ingress && ${OC} delete secret router-certs -n openshift-ingress

	${OC} create secret tls router-certs --cert=${CERTDIR}/fullchain.pem --key=${CERTDIR}/key.pem -n openshift-ingress && \
	${OC} patch ingresscontroller default -n openshift-ingress-operator --type=merge --patch='{"spec": { "defaultCertificate": { "name": "router-certs" }}}'
}

install_cert
configure_router_certs
