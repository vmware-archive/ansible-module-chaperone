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
Short_description: Query vCenter for moId ID
description:
    Module will return moId id for given vcenter object name
requirements:
    - ansible 2.x
    - pyvmomi 5.x +
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    username:
        description:
            - The username of the vSphere vCenter with Admin rights
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter user
        required: True
        aliases: ['pass', 'pwd']
    vcenter_object_name:
        description:
            - vCenter inventory object name
        required: True
        default: Null
    vcenter_vim_type:
        description:
            - vCenter resource type valid options are
            - cluster, datacenter, datastore, vds, dvs-port, vm, folder
        required: True
        default: Null
'''

EXAMPLES = '''
- name: Get External Network Portgroup MOID
  vcenter_query:
    hostname: "{{ vio_oms_vcenter_hostname }}"
    username: "{{ vio_oms_vcenter_username }}"
    password: "{{ vio_oms_vcenter_pwd }}"
    validate_certs: False
    vcenter_object_name: "{{ vio_val_extnet_portgroup }}"
    vcenter_vim_type: "dvs-port"
  register: ext_net_portgroup_moid
  tags:
    - validate_openstack
'''

try:
    import json
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

VIM_TYPE = {
    'cluster': [vim.ClusterComputeResource],
    'datacenter': [vim.Datacenter],
    'datastore': [vim.Datastore],
    'vds': [vim.dvs.VmwareDistributedVirtualSwitch],
    'dvs-port': [vim.Network],
    'vm': [vim.VirtualMachine],
    'folder': [vim.Folder],
}


def find_vcenter_object_by_name(content, vimtype, object_name):

    vcenter_mos = get_all_objs(content, vimtype)

    for mo, mo_name in vcenter_mos.items():
        if mo_name == object_name:
            return mo
    return None


def main():

    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            vcenter_object_name=dict(type='str', required=True),
            vcenter_vim_type=dict(type='str', required=True),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    object_id = None

    content = connect_to_api(module)

    vcenter_mo = find_vcenter_object_by_name(content,
                                             VIM_TYPE[module.params['vcenter_vim_type']],
                                             module.params['vcenter_object_name'])

    if vcenter_mo:
        object_id = vcenter_mo._moId
    else:
        module.fail_json(msg="Failed to get MOID for: {}".format(module.params['vcenter_object_name']))

    module.exit_json(changed=False, object_id=object_id)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
