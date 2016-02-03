#!/usr/bin/python
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


DOCUMENTATION = '''
---
module: vcenter_query
Short_description: Query vCenter for inventory id by inventory name and return custom fact
description:
    - Provides an interface to query vcenter, return id as specified custom fact
versoin_added: "0.1"
options:
    vcenter_object_name:
        description:
            - vCenter inventory object name
        required: True
        default: Null
    ansible_variable_name:
        description:
            - Valid Ansible variable name for custom fact setting to returned id
        required: True
        default: Null
    vcenter_vim_type:
        description:
            - vCenter resource type valid options are
            - cluster, datacenter, datastore, dvs, dvs-port, vm, folder
        required: True
        default: Null
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
    vcenter_object_name: "{{ vio_cluster_mgmt }}"
    ansible_variable_name: 'your_var_name'
    vcenter_vim_type: 'cluster'

- name: test new custom var
  debug: msg="New var value --> {{ your_var_name }}"
'''

try:
    import json
except ImportError:
    import simplejson as json

import atexit

import ssl
if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
except ImportError:
    print("failed=True msg='pyVmomi is required to run this module'")



VIM_TYPE = {
    'cluster': vim.ClusterComputeResource,
    'datacenter': vim.Datacenter,
    'datastore': vim.Datastore,
    'vds': vim.DistributedVirtualSwitch,
    'dvs-port': vim.Network,
    'vm': vim.VirtualMachine,
    'folder': vim.Folder,
}

def connect_to_vcenter(module, disconnect_atexit=True):
    hostname = module.params['host']
    username = module.params['login']
    password = module.params['password']
    port = module.params['port']

    try:
        service_instance = SmartConnect(
            host=hostname,
            user=username,
            pwd=password,
            port=port
        )

        if disconnect_atexit:
            atexit.register(Disconnect, service_instance)

        return service_instance.RetrieveContent()
    except vim.fault.InvalidLogin, invalid_login:
        module.fail_json(msg=invalid_login.msg, apierror=str(invalid_login))


def get_all_objects(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj


def find_vcenter_object_by_name(content, vimtype, object_name):
    vcenter_object = get_all_objects(content, [vimtype])

    for k, v in vcenter_object.items():
        if v == object_name:
            return k._moId
    else:
        return None

def core(module):

    vcenter_object_name = module.params['vcenter_object_name']
    vcenter_object_type = module.params['vcenter_vim_type']

    try:
        vim_type = VIM_TYPE[vcenter_object_type]
    except KeyError:
        module.fail_json(msg="Invalid vim type specified: %s" % vcenter_object_type)

    content = connect_to_vcenter(module)

    object_moid = find_vcenter_object_by_name(
        content,
        vim_type,
        vcenter_object_name
    )

    if object_moid:
        return False, object_moid
    else:
        return True, "Failed to obtain moId for: %s" % vcenter_object_name


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            vcenter_object_name=dict(type='str', required=True),
            ansible_variable_name=dict(type='str', required=True),
            vcenter_vim_type=dict(type='str', required=True),
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

        vcenter_moid = result
        ansible_var_name = module.params['ansible_variable_name']
        ansible_facts_dict['ansible_facts'].update({ansible_var_name: vcenter_moid})
        ansible_facts_dict['changed'] = True
        print json.dumps(ansible_facts_dict)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()

