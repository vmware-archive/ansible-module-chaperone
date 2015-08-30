#!/usr/bin/env python
#
#  Copyright 2015 VMware, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

try:
    import json
except ImportError:
    import simplejson as json

import re
import os
import time
import atexit
import urllib2
import datetime
import ast

import ssl

if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
except ImportError:
    print("failed=True msg='pyVmomi is required to run this module'")

DOCUMENTATION = '''
---
module: dc_cluster
Short_description: Create Datacenter and clusters in vCenter
description:
    - Provides an interface to add datacenters and clusters to a vCenter instance.
version_added: "0.1"
options:
    host:
        description:
            - Address to connect to the vCenter instance.
        required: True
        default: null
    login:
        description:
            - Username to login to vCenter instance.
        required: True
        default: null
    password:
        description:
            - Password to authenticate to vCenter instance.
        required: True
        default: null
    port:
        description:
            - Port to access vCenter instance.
        required: False
        default: 443
    datacenter:
        description:
            - Datacenter structure that is expected to be created on the vCenter instance.
        required: True
        default: null

author: Devin Nance, Jake Dupuy
'''


class Createdatacenter(object):
    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except:
            creds = vhost + " " + user + " " + password
            self.module.fail_json(msg='Cannot connect %s' % creds)
        return self.SI

    def get_content(self, connection):
        try:
            content = connection.RetrieveContent()
        except Exception as e:
            return False, dict(msg=str(e))
        return content

    def create_configspec(self):
        default_vmsettings = vim.cluster.DasVmSettings(restartPriority="high")
        das_config = vim.cluster.DasConfigInfo(enabled=True,
                                               admissionControlEnabled=True,
                                               failoverLevel=1,
                                               hostMonitoring="enabled",
                                               vmMonitoring="vmAndAppMonitoring",
                                               defaultVmSettings=default_vmsettings)
        drs_config = vim.cluster.DrsConfigInfo(enabled=True,
                                               defaultVmBehavior="fullyAutomated")
        cluster_config = vim.cluster.ConfigSpecEx(dasConfig=das_config,
                                                  drsConfig=drs_config)
        return cluster_config

    def create_dc(self, connection, datacenter_name):
        try:
            content = self.get_content(connection)
            folder = content.rootFolder
            dc = folder.CreateDatacenter(name=datacenter_name)
        except vmodl.MethodFault as meth_fault:
            return True, dict(msg=meth_fault.msg)
        except vmodl.RuntimeFault as run_fault:
            return True, dict(msg=run_fault.msg)
        return False, dc

    def create_dc_clusters(self, dc, cluster_name, cluster_spec):
        try:
            root_dc = dc
            host_folder = root_dc.hostFolder
            vio_cluster = host_folder.CreateClusterEx(name=cluster_name, spec=cluster_spec)
        except vmodl.MethodFault as meth_fault:
            return True, dict(msg=meth_fault.msg)
        except vmodl.RuntimeFault as run_fault:
            return True, dict(msg=run_fault.msg)
        return False, vio_cluster

def core(module):
    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    vio_dc = module.params.get('datacenter', dict())

    dc_name = vio_dc['name']
    cluster_list = []

    for cluster in vio_dc['clusters']:
        cluster_name = cluster['name']
        cluster_list.append(cluster_name)

    v = Createdatacenter(module)
    c = v.si_connection(vcsvr, vuser, vpass, vport)
    vconfig_spec = v.create_configspec()
    dc_status, vio_dc = v.create_dc(c, dc_name)

    if not dc_status and type(vio_dc) is vim.Datacenter:
        for cluster in cluster_list:
            new_cluster_status, new_cluster = v.create_dc_clusters(vio_dc, cluster, vconfig_spec)
        if not new_cluster_status and type(new_cluster) is vim.ClusterComputeResource:
            return new_cluster_status, dict(msg='Created Datacenter and Clusters')
        else:
            return new_cluster_status, dict(msg=new_cluster)
    else:
        return dc_status, dict(msg=vio_dc)

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            datacenter=dict(type='dict', required=True)
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(changed=False, msg=result)
    else:
        module.exit_json(changed=True, msg=result)

from ansible.module_utils.basic import *
main()
