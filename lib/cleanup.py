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
#
# Python script using the boto library to delete route53 zones and records,
# cause the awscli seems too sucky with deletion (you need to pass a big xml
# blob to it)
#
# You need the credentials setup with whatever means in ~/.aws or via env
# variables.
#
# After the 'reaper' has reaped our openshift install in the aws account, it
# forget to delete some A records, so the reinstall fails :((
# let's be helpful and do it for the reaper....
#

import argparse
import sys
import os

import boto


class NoGoZoneIsANogo(Exception):
    pass


def delete_hosted_zone(route53, zonename, silent):
    zone = route53.get_zone(zonename)
    if not zone:
        if not silent:
            print("Could not find " + zonename)
        return
    records = zone.get_records()

    if not silent:
        print("Deleting zone: " + zonename)
    for rec in records:
        if rec.type in ('NS', 'SOA'):
            continue
        zone.delete_record(rec)
        if not silent:
            print("\tdeleted record " + rec.name)

    if not silent:
        print("Zone " + zonename + " has been deleted.")
    zone.delete()


def delete_record(route53, zonename, recordname, silent):
    if not zonename.endswith("."):
        zonename += "."
    if not recordname.endswith("."):
        recordname += "."

    zone = route53.get_zone(zonename)
    if not zone:
        raise NoGoZoneIsANogo("Could not find zone for " + zonename)

    record = zone.get_a(recordname)
    if not record:
        if not silent:
            print("Could not find record " + recordname)
        return

    if not silent:
        print("Record " + record.name + " has been deleted.")
    zone.delete_a(record.name)


def check_for_credential_file():
    if 'AWS_SHARED_CREDENTIALS_FILE' not in os.environ:
        return (None, None)
    path = os.environ['AWS_SHARED_CREDENTIALS_FILE']
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)
    aws_access_key_id = None
    aws_secret_access_key = None

    if os.path.isfile(path):
        fp = open(path)
        lines = fp.readlines()
        fp.close()
        for line in lines:
            if line[0] != '#':
                if '=' in line:
                    name, value = line.split('=', 1)
                    if name.strip() == 'aws_access_key_id':
                        value = value.strip()
                        aws_access_key_id = value
                    elif name.strip() == 'aws_secret_access_key':
                        value = value.strip()
                        aws_secret_access_key = value
    return (aws_access_key_id, aws_secret_access_key)


def cleanup_dns_names(clustername, base_domain, silent=False):
    zonename = clustername + '.' + base_domain
    aws_access_key_id, aws_secret_access_key = check_for_credential_file()
    route53 = boto.connect_route53(aws_access_key_id, aws_secret_access_key)

    delete_hosted_zone(route53, zonename, silent)
    delete_record(route53, base_domain, "api." + zonename, silent)
    delete_record(route53, base_domain, "\\052.apps." + zonename, silent)
