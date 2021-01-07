# Moumoustall - Openshift on Openstack (PSI) installer

Install multi openstack clouds
==============================

Install multiple opnestack clouds with different versions, 

It supports : 

- yaml based configuration.
- multiple profiles for diffrent version
- uninstall, clean up automatically
- adding htpasswd
- scale down to 3 nodes
- create letsecnrypt certs on router if you have  acme.sh installed and configured.

And will support in the future :

- retries on failures
- queuing by resources, if you have too many clusters spawn it will tell you or queu it.

See [config yaml](./config/config.yaml.default) to see how to configure it.

## Name

I have no idea where the name comes from just a word passing my head while trying to figure out how to call it....

if you google Moumou you end up with this https://www.idello.org/fr/ressource/23131-Moumou-La-Mouffette-La-Consonne-m so I guess that become the official logo and a reason??

![inline](https://rlv.zcache.be/carreau_illustration_audacieuse_de_mouffette_avec_les-rad64bb3c467248cdb079a35b62af128c_agtk1_8byvr_307.jpg?rvtype=content)
