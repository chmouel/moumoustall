# -*- coding: utf-8 -*-
# Author: Chmouel Boudjnah <chmouel@chmouel.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

from lib import cleanup, downloader, route53
from lib.cleanup import cleanup_dns_names

PROFILE = {
    "ci-45": {
        "template": "default",
        "osCloud": "qapipeline",
        "baseDomain": "devcluster.openshift.com",
        "clusterName": "ci-pipeline-45",
        "externalNetwork": "provider_net_cci_9",
        "installerVersion": "latest-4.5",
        "onlyMasters": True,
        "pullRequestJsonFile": "pull.secret.json",
    }
}


def execute(command, check_error=""):
    """Execute commmand"""
    result = ""
    try:
        result = subprocess.run(["/bin/sh", "-c", command],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                check=True)
    except subprocess.CalledProcessError as exception:
        if check_error:
            print(check_error)
            print(
                f"Status code: {exception.returncode}: Output: \n{exception.output}"
            )
            raise exception
    return result


def create_floating_ips(cluster_name, base_domain, os_cloud, external_network):
    cmd = f"openstack --os-cloud {os_cloud} floating ip create -f json --description 'cluster: {cluster_name} , api.{cluster_name}.{base_domain}' {external_network}"
    ret = execute(cmd, check_error=f"Error running {cmd}")
    jeez = json.loads(ret.stdout)
    apiip = jeez['floating_ip_address']

    cmd = f"openstack --os-cloud {os_cloud} floating ip create -f json --description 'cluster: {cluster_name} , *.apps.{cluster_name}.{base_domain}' {external_network}"
    ret = execute(cmd, check_error=f"Error running {cmd}")
    jeez = json.loads(ret.stdout)
    appsip = jeez['floating_ip_address']

    return {"api": apiip, "apps": appsip}


def do_template(config, api_ip, apps_ip):
    path = pathlib.Path("config") / f"install-{config['template']}.yaml"
    if not path.exists():
        raise Exception(f"{path} doesnt exist")

    def tpl_apply(param):
        if param == "lbFloatingIP":
            return api_ip
        elif param == "ingressFloatingIP":
            return apps_ip
        elif param == "pullSecret":
            return open(f"./config/{config['pullRequestJsonFile']}",
                        'r').read()
        elif param in config:
            return config[param]
        raise Exception(f"Cannot replace {{{param}}} variable")

    return re.sub(
        r"\{\{([_a-zA-Z0-9\.]*)\}\}",
        lambda m: tpl_apply(m.group(1)),
        path.read_text(),
    )


def post_install_tasks(config, install_dir, apps_ip):
    authjson = pathlib.Path(install_dir) / "metadata.json"
    authjson = json.load(authjson.open())

    if 'onlyMasters' in config and config['onlyMasters']:
        print(f"🌆 Scaling down clusters to only masters")
        os.system(
            f"bash scripts/scale-to-three-node.sh {install_dir}/auth/kubeconfig >/dev/null"
        )

    infraID = authjson['infraID']
    print(f"🌸 Assigning floating ip for {infraID}-ingress-port")
    cmd = f"openstack --os-cloud {config['osCloud']} floating ip set --port {infraID}-ingress-port {apps_ip}"
    execute(cmd, check_error=f"Error running {cmd}")
    print(f"🗽 Creating letsencrypt certs for router")
    os.system(
        f"bash scripts/install-router-cert.sh {authjson['clusterName']} >/dev/null"
    )


def uninstall_cluster(config, install_binary):
    install_dir = pathlib.Path("installs") / config['clusterName']
    print("⚰️ Cleaning cluster resources")
    ret = os.system(
        f"{install_binary} destroy cluster --dir={install_dir} --log-level=debug"
    )
    if ret != 0:
        raise Exception("Failure to destroy cluster")

    print(
        f"🧹 Cleaning old DNS names for {config['clusterName']}.{config['baseDomain']}"
    )
    cleanup.cleanup_dns_names(config['clusterName'],
                              config['baseDomain'],
                              silent=True)

    print(
        f"⚒ Cleaning floating IPS {config['clusterName']}.{config['baseDomain']}"
    )
    ret = os.system(
        f"bash ./scripts/remove-floating-ips.sh {config['clusterName']} {config['osCloud']}"
    )

    if ret != 0:
        raise Exception("Could not cleanup floating ips.")


def doprofile(config, args):
    # make sure this is unset
    os.environ["OS_CLOUD"] = ""
    install_dir = pathlib.Path("installs") / config['clusterName']
    print(f"🧢 Downloading latest binary for {config['installerVersion']}")
    binaries_dir = pathlib.Path("binaries")
    binaries_dir.mkdir(parents=True, mode=0o755)
    install_binary = downloader.download_installer(config["installerVersion"],
                                                   binaries_dir)

    if install_dir.exists():
        if args.uninstall:
            uninstall_cluster(config, install_binary)
        else:
            raise Exception(f"{str(install_dir)} exists already")
    install_dir.mkdir(parents=True, mode=0o755)

    cleanup.cleanup_dns_names(config['clusterName'],
                              config['baseDomain'],
                              silent=True)
    print(
        f"🛢  Creating Floating IPS for {config['clusterName']}.{config['baseDomain']}"
    )
    ips = create_floating_ips(config['clusterName'], config['baseDomain'],
                              config['osCloud'], config['externalNetwork'])

    print(
        f"🎛  Creating DNS for {config['clusterName']}.{config['baseDomain']} with {ips['api']} and {ips['apps']}"
    )
    dns = route53.Route53Provider(config['clusterName'], config['baseDomain'])
    dns.add_api_domain(ips['api'])
    dns.add_apps_domain(ips['apps'])

    print(f"🧶 Generating install-config.yaml in {install_dir}")
    processed = install_dir / "install-config.yaml"
    processed.write_text(do_template(config, ips["api"], ips["apps"]))

    print(
        f"🧨 Launching installer in {install_dir}, tail -f installs/{config['clusterName']}/.openshift_install.log for giggles 🙊"
    )
    ret = os.system(
        f"{install_binary} create cluster --dir={install_dir} --log-level=info"
    )
    if ret != 0:
        print("👊 It's up to you to debug why it failed!!")
        sys.exit(1)

    post_install_tasks(
        config,
        f"installs/{config['clusterName']}",
        ips["apps"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall",
                        "-u",
                        help="Uninstall profile if it's here already",
                        action="store_true",
                        default=False)
    parser.add_argument("--all-profiles",
                        "-a",
                        help="Run for all profiles",
                        action="store_true",
                        default=False)
    parser.add_argument("profiles", nargs="*")
    args = parser.parse_args(sys.argv[1:])
    if args.all_profiles:
        profiles = PROFILE.keys()
    elif not args.profiles:
        print("Missing profile as argument")
        parser.print_help()
        sys.exit(2)
    else:
        profiles = args.profiles

    for profile in profiles:
        if not profile in PROFILE:
            raise Exception(f"Profile: {profile} is not in config")
        config = PROFILE[profile]
        doprofile(args, config)


if __name__ == "__main__":
    main()
