#!/usr/bin/env python3
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
import yaml

from lib import cleanup, downloader, route53


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

    if 'htpasswd' in config:
        print(f"👪  Creating extras users from config/{config['htpasswd']}")
        os.system(
            f"bash scripts/add-oauth-htpasswd.sh {install_dir}/auth/kubeconfig config/{config['htpasswd']} >/dev/null"
        )

    if 'onlyMasters' in config and config['onlyMasters']:
        print(f"🌆 Scaling down clusters to only masters")
        os.system(
            f"bash scripts/scale-to-three-node.sh {install_dir}/auth/kubeconfig >/dev/null"
        )

    infraID = authjson['infraID']
    print(f"🌸 Assigning floating ip for {infraID}-ingress-port")
    cmd = f"openstack --os-cloud {config['osCloud']} floating ip set --port {infraID}-ingress-port {apps_ip}"
    execute(cmd, check_error=f"Error running {cmd}")

    if os.path.exists(os.path.expanduser("~/.acme.sh/acme.sh")):
        print(f"🗽 Creating letsencrypt certs for router")
        os.system(
            f"bash scripts/install-router-cert.sh {authjson['clusterName']} >/dev/null"
        )


def uninstall_cluster(config, install_binary):
    install_dir = pathlib.Path("installs") / config['clusterName']
    print("⚰️  Cleaning old cluster resources")
    ret = os.system(f"{install_binary} destroy cluster --dir={install_dir}")
    if ret != 0:
        raise Exception("Failure to destroy cluster")

    print(
        f"🧹 Cleaning old DNS names for {config['clusterName']}.{config['baseDomain']}"
    )
    cleanup.cleanup_dns_names(config['clusterName'],
                              config['baseDomain'],
                              silent=True)

    print(
        f"🔱 Cleaning floating IPS for cluster {config['clusterName']}.{config['baseDomain']}"
    )
    ret = os.system(
        f"bash ./scripts/remove-floating-ips.sh {config['clusterName']} {config['osCloud']}"
    )
    if ret != 0:
        raise Exception("Could not cleanup floating ips.")


def doprofile(args, config):
    # make sure this is unset
    os.environ["OS_CLOUD"] = ""
    install_dir = pathlib.Path("installs/") / config['clusterName']
    print(
        f"🌊 Downloading openshift installer for version {config['installerVersion'].replace('latest-', '')}"
    )
    binaries_dir = pathlib.Path("binaries")
    if not binaries_dir.exists():
        binaries_dir.mkdir(parents=True, mode=0o755)
    installer_channel = "installer_channel" in config and config[
        'installer_channel'] or 'prod'
    install_binary = downloader.download_installer(config["installerVersion"],
                                                   binaries_dir,
                                                   source=installer_channel)
    if (install_dir / "metadata.json").exists():
        if args.uninstall:
            uninstall_cluster(config, install_binary)
        else:
            raise Exception(f"{str(install_dir)} exists already")

    if not install_dir.exists():
        install_dir.mkdir(parents=True, mode=0o755)

    cleanup.cleanup_dns_names(config['clusterName'],
                              config['baseDomain'],
                              silent=True)
    if args.no_install:
        return

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
    parser.add_argument(
        "--no-install",
        "-N",
        help="Do not install, combined to -u you will do just an uninstall",
        action="store_true",
        default=False)
    parser.add_argument("--list-profiles",
                        "-L",
                        help="List all profiles available",
                        action="store_true",
                        default=False)

    parser.add_argument("--config-file",
                        default="./config/config.yaml",
                        help="path to config file with profiles")

    parser.add_argument("--all-profiles",
                        "-a",
                        help="Run for all profiles",
                        action="store_true",
                        default=False)
    parser.add_argument("profiles", nargs="*")
    args = parser.parse_args(sys.argv[1:])

    CONFIG = yaml.safe_load(open(args.config_file, 'r'))

    if args.list_profiles:
        print("Profiles available:")
        print("-------------------")
        for profile in CONFIG.keys():
            metadatajson = pathlib.Path(
                "installs") / CONFIG[profile]['clusterName'] / 'metadata.json'
            installed = ""
            if metadatajson.exists():
                installed = "Installed"
            print("%-10s%-10s" % (profile, installed))
        sys.exit(0)

    if args.all_profiles:
        profiles = CONFIG.keys()
    elif not args.profiles:
        print("Missing profile as argument")
        parser.print_help()
        sys.exit(2)
    else:
        profiles = args.profiles

    for profile in profiles:
        if profile not in CONFIG:
            raise Exception(f"Profile: {profile} is not in config")
        config = CONFIG[profile]
        doprofile(args, config)


if __name__ == "__main__":
    main()
