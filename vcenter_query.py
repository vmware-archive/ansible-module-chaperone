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
module: vcenter_query
Short_description: Query vCenter for inventory id by inventory name and return custom fact
description:
    - Provides an interface to query vcenter, return id as specified custom fact
versoin_added: "0.1"
options:
    host:
    resourcename:
        description:
            - vCenter inventory object name
        required: True
        default: Null
    resourcevarname:
        description:
            - Valid Ansible variable name for custom fact setting to returned id
        required: True
        default: Null
    resourcetype:
        description:
            - vCenter resource type valid options are
            - cluster, datacenter, datastore, dvs, dvs-port, vm
        required: True
        default: Null
    getfacts:
        description:
            - valid options
        required: False
        default: yes
'''
EXAMPLES = '''
- name: Get vCenter ID
  ignore_errors: no
  local_action:
    module: vcenter_query
    host: vcenter_host
    login: vcenter_user
    password: vcenter_password
    port: vcenter_port
    resourcename: "{{ item.vcenter_object_name }}"
    resourcevarname: "{{ item.vcenter_object_var }}"
    resourcetype: 'cluster'
    getfacts: 'yes'
  with_items:
    - { vcenter_object_name: "{{ vio_cluster_mgmt }}", vcenter_object_var: 'vio_cluster_mgmt_id' }
    - { vcenter_object_name: "{{ vio_cluster_edge }}", vcenter_object_var: 'vio_cluster_edge_id' }
    - { vcenter_object_name: "{{ vio_cluster_compute }}", vcenter_object_var: 'vio_cluster_compute_id' }
'''

class Getnamesids(object):
    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except:
            creds = vhost + " " + user + " " + password
            self.module.fail_json(msg='Could not connect to: %s' % creds)
        return self.SI

    def get_content(self, connection):
        try:
            content = connection.RetrieveContent()
        except Exception as e:
            return str(e)
        return content

    def get_ids_dc(self, connection, vimtype):
        try:
            content = self.get_content(connection)
            name_id = {}
            container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
            for managed_object_ref in container.view:
                mor_id = str(managed_object_ref).split(':')[1].replace("'", "")
                name_id.update({managed_object_ref.name: mor_id})
            return False, name_id
        except vmodl.MethodFault as meth_fault:
            return True, dict(msg=meth_fault.msg)
        except vmodl.RuntimeFault as runtime_fault:
            return True, dict(msg=runtime_fault.msg)

    def get_id_name(self, connection, vimtype, target_name):
        try:
            status, vc_objts = self.get_ids_dc(connection, vimtype)
            if not status and target_name in vc_objts:
                for k, v in vc_objts.iteritems():
                    if k == target_name:
                        return False, v
            elif target_name not in vc_objts:
                return True, dict(msg="Target Name: %s not Found" % target_name)
        except Exception as e:
            return True, dict(msg="ERROR: %s" % str(e))

def core(module):

    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    rec_name = module.params.get('resourcename')
    rec_type = module.params.get('resourcetype')

    vim_rec_type = {
        'cluster': vim.ClusterComputeResource,
        'datacenter': vim.Datacenter,
        'datastore': vim.Datastore,
        'dvs': vim.DistributedVirtualSwitch,
        'dvs-port': vim.Network,
        'vm': vim.VirtualMachine
    }
    names_ids = Getnamesids(module)
    connect = names_ids.si_connection(vcsvr, vuser, vpass, vport)
    vim_type = vim_rec_type[rec_type]

    try:
        id_status, vc_id = names_ids.get_id_name(connect, [vim_type], rec_name)
        return id_status, vc_id
    except Exception as a:
        return True, dict(msg=str(a))


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            resourcename=dict(type='str', required=True),
            resourcevarname=dict(type='str', required=True),
            resourcetype=dict(type='str', required=True),
            getfacts=dict(default="yes", required=False)
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(msg=result)
    else:
        ansible_facts_dict = {
            "changed": False,
            "ansible_facts": {

            }
        }

        resource_id = result
        resource_var = module.params.get('resourcevarname')
        ansible_facts_dict['ansible_facts'].update({resource_var: resource_id})
        ansible_facts_dict['changed'] = True
        print json.dumps(ansible_facts_dict)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()

