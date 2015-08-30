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
module: add_nfs_ds
Short_description: Create NFS datastore and attache to all hosts in all cluster in datacenter
description:
    - Provides an interface to add nfs datastore to all hosts in clusters.
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
    nfshost:
        description:
            - hostname/ip of the nfs service.
        required: True
        default: null
    nfspath:
        description:
            - path to nfs share ex: /nfs
        required: True
        default: null
    nfsname:
        description:
            - name of nfs datastore in vcenter
        required: True
        default: null
    nfsaccess:
        description:
            - type of access if not readWrite specified on the nfs service, module will fail
        required: False
        default: readWrite
    nfstype:
        description:
            - type of datastore specified, NFSv3/4
        required: False
        default: NFS
'''

class Createdsnfs(object):
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
            return content
        except vmodl.MethodFault as e:
            return module.fail_json(msg=e.msg)

    def get_vcobjt_byname(self, connection, vimtype, target_name):
        content = self.get_content(connection)
        vc_objt = {}
        try:
            container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
            for managed_object_ref in container.view:
                vc_objt.update({managed_object_ref.name: managed_object_ref})
            for k, v in vc_objt.items():
                if k == target_name:
                    return False, v
        except vmodl.MethodFault as method_fault:
            return True, dict(msg=method_fault.msg)
        except vmodl.RuntimeFault as runtime_fault:
            return True, dict(msg=runtime_fault.msg)

    def nas_spec(self, nfshost, nfspath, nfsname, nfsaccess, nfstype):
        nas_spec = vim.host.NasVolume.Specification(remoteHost=nfshost,
                                                    remotePath=nfspath,
                                                    localPath=nfsname,
                                                    accessMode=nfsaccess,
                                                    type=nfstype)
        return nas_spec

    def create_nfs(self, cluster, nasconfigspec):
        try:
            hosts = cluster.host
            for host in hosts:
                host.configManager.datastoreSystem.CreateNasDatastore(spec=nasconfigspec)
        except vim.HostConfigFault as hostconfig_fault:
            return True, dict(msg=hostconfig_fault.msg)
        except vmodl.MethoFault as method_fault:
            return True, dict(msg=method_fault.msg)
        return False, dict(msg="Attached all hosts in %s cluster to nfs datastore" % cluster.name)

def core(module):
    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    vnfshost = module.params.get('nfshost')
    vnfspath = module.params.get('nfspath')
    vnfsname = module.params.get('nfsname')
    vnfsaccess = module.params.get('nfsaccess')
    vnfstype = module.params.get('nfstype')
    target_cluster_name = module.params.get('cluster')
    
    vnfs = Createdsnfs(module)
    connection = vnfs.si_connection(vcsvr, vuser, vpass, vport)

    try:
        cluser_status, target_cluster = vnfs.get_vcobjt_byname(connection , [vim.ClusterComputeResource], target_cluster_name)
        if not cluster_status:
            nas_specification = vnfs.nas_spec(vnfshost, vnfspath, vnfsname, vnfsaccess, vnfstype)
            nfs_status, nfs_msg = vnfs.create_nfs(target_cluster, nas_specification)
            if not nfs_status:
                return False, nfs_msg
            else:
                return True, nfs_msg
    except Exception as e:
        return True, str(e)

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            cluster=dict(type='str', required=True),
            nfshost=dict(type='str', required=True),
            nfspath=dict(type='str', required=True),
            nfsname=dict(type='str', required=True),
            nfsaccess=dict(type='str', required=False, default='readWrite'),
            nfstype=dict(type='str', required=False, default='NFS')
        )
    )

    try:
        fail, result = core(module)
        if fail:
            module.fail_json(msg=result)
        else:
            module.exit_json(msg=result)
    except Exception as e:
        import traceback
        module.fail_json(msg='%s: %s\n%s' % (e.__class__.__name__, str(e), traceback.format_exc()))

from ansible.module_utils.basic import *
