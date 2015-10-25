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

import atexit
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
    vcenter_object_name:
        description:
            - vCenter inventory object name target
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
            - cluster, datacenter, datastore, dvs, dvs-port, vm
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
    vcenter_vim_type: 'cluster'
    ansible_variable_name: 'my_new_var_name'

- name: test new custom var
  debug: msg="New var value --> {{ your_var_name }}"
'''

def si_connect(module):
    try:
        si = SmartConnect(host=module.params['host'],
                          user=module.params['login'],
                          pwd=module.params['password'],
                          port=module.params['port'])
    except:
        failmsg = "Could not connect to virtualserver"
        module.fail_json(msg=failmsg)

    atexit.register(Disconnect, si)

    return si

def get_id(module, si, vimtype, name, getobject=None, getmoid=None):
    '''
    :param si service instance
    :param vimtype: valid vim type
    :param name: name of the target (module.params.get('vcenter_object_name'))
    :param getobject: specify True if wanting to return the target object
    :param getmoid: specify True if wanting to return the moId property
    '''
    try:
        content = si.RetrieveContent()
        limit = content.rootFolder
        container = content.viewManager.CreateContainerView(limit, vimtype, True)

        if name:
            for x in container.view:
                if x.name == name:
                    if getmoid:
                        return str(x._moId)
                    if getobject:
                        return x
                else:
                    module.fail_json(msg="Could not find specified name: {}".format(name))
        else:
            module.fail_json(msg="Please specify a vcenter object name")

    except Exception as e:
        module.fail_json(msg="Failed to get id for: {} error: {}".format(name, e))


def core(module):

    vim_type = module.params['vcenter_vim_type']
    vcenter_object_name = module.params['vcenter_object_name']

    vim_rec_type = {
        'cluster': vim.ClusterComputeResource,
        'datacenter': vim.Datacenter,
        'datastore': vim.Datastore,
        'vds': vim.DistributedVirtualSwitch,
        'dvs-port': vim.Network,
        'vm': vim.VirtualMachine
    }

    try:
        vimtype = vim_rec_type[vim_type]
    except KeyError:
        module.fail_json(msg="Please specify valid vim type: cluster, datacenter, datastore, vds, vm")

    si = si_connect(module)

    vcenter_id = get_id(module, si,
                        [vimtype],
                        vcenter_object_name,
                        False, True)

    return False, vcenter_id


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            vcenter_object_name=dict(type='str'),
            vcenter_vim_type=dict(type='str'),
            ansible_variable_name=dict(type='str')
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(changed=False, msg=result)
    else:
        ansible_facts_dict = {
            "changed": False,
            "ansible_facts": {

            }
        }

        resource_id = result
        var = module.params.get('ansible_variable_name')
        ansible_facts_dict['ansible_facts'].update({var: resource_id})
        ansible_facts_dict['changed'] = True
        print json.dumps(ansible_facts_dict)


from ansible.module_utils.basic import *
from ansible.module_utils.facts import *

if __name__ == "__main__":
    main()
