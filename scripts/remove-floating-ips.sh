#!/usr/bin/env bash
CLUSTER=$1

[[ -z ${1} ]] && exit 1

export OS_CLOUD=${2:-qapipeline}

openstack floating ip list -f json --long >/tmp/floating-ip.json

ITEMS=$(jq -r '.[] | select (.Description|test("cluster: '"$CLUSTER"' "))."Floating IP Address"' /tmp/floating-ip.json)

for ITEM in $ITEMS; do
    echo "⦾ Removing floating IP: ${ITEM}"
    openstack floating ip delete $ITEM
done
