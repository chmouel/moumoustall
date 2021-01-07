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
