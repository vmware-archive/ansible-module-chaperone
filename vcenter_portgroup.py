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
module: vcenter_portgroup
short_description: Manage VMware vSphere VDS Portgroup
description:
	- Manage VMware vCenter portgroups in a given virtual distributed switch
version_added: 1.0
author: '"Daniel Kim" <kdaniel () vmware.com>'
notes:
	- Tested on vSphere 5.5
requirements:
	- "python >= 2.6"
	- PyVmomi
options (all of them are str type):
	hostname:
		description:
			- The hostname or IP address of the vSphere vCenter API server
		required: True
	vs_port:
		description:
			- The port to be used to connect to the vsphere host
		required: False
	username:
		description:
			- The username of the vSphere vCenter
		required: True
		aliases: ['user', 'admin']
	password:
		description:
			- The password of the vSphere vCenter
		required: True
		aliases: ['pass', 'pwd']
	vds_name:
		description:
			- The name of the distributed virtual switch where the port group is added to.
				The vds must exist prior to adding a new port group, otherwise, this
				process will fail.
		required: True
	port_group_name:
		description:
			- The name of the port group the cluster will be created in.
		required: True
	port_binding:
		description:
			- Available port binding types - static, dynamic, ephemeral
		required: True
	port_allocation:
		description:
			- Allocation model of the ports - fixed, elastic
			- Fixed allocation always reserve the number of ports requested
			- Elastic allocation increases/decreases the number of ports as needed
		required: True
	numPorts:
		description:
			- The number of the ports for the port group
			- Default value will be 0 - no ports
	state:
		description:
		- If the port group should be present or absent
		choices: ['present', 'absent']
		required: True
'''
EXAMPLES = '''
# Example vmware_datacenter command from Ansible Playbooks
- name: Create Port Group
	local_action: >
		vPortgroup
		hostname="{{ vSphere_host }}" username=root password=vmware
		vsphere_port="443"
		port_group_name="test_port_grp1"
		num_ports="8"
'''
try:
    from pyVmomi import vim, vmodl
    from pyVim import connect

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

import ssl

if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

import time


def wait_for_task(task):
    while True:
        if task.info.state == vim.TaskInfo.State.success:
            return True, task.info.result
        if task.info.state == vim.TaskInfo.State.error:
            try:
                raise TaskError(task.info.error)
            except AttributeError:
                raise TaskError("An unknown error has occurred")
        if task.info.state == vim.TaskInfo.State.running:
            time.sleep(10)
        if task.info.state == vim.TaskInfo.State.queued:
            time.sleep(10)


def get_all_objs(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj


def find_vds_by_name(content, vds_name):
    vdSwitches = get_all_objs(content, [vim.dvs.VmwareDistributedVirtualSwitch])
    for vds in vdSwitches:
        if vds_name == vds.name:
            return vds
    return None


def find_vdspg_by_name(vdSwitch, portgroup_name):
    portgroups = vdSwitch.portgroup
    for pg in portgroups:
        if pg.name == portgroup_name:
            return pg
    return None


def check_port_group_state(module):
    vds_name = module.params['vds_name']
    port_group_name = module.params['port_group_name']
    try:
        content = module.params['content']
        vds = find_vds_by_name(content, vds_name)
        if vds is None:
            module.fail_json(msg='Target distributed virtual switch does not exist!')
        port_group = find_vdspg_by_name(vds, port_group_name)
        module.params['vds'] = vds
        if port_group is None:
            return 'absent'
        else:
            module.params['port_group'] = port_group
            return 'present'
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_exit_unchanged(module):
    module.exit_json(changed=False)


def state_destroy_port_group(module):
    # TODO
    module.exit_json(changed=False)


def state_create_port_group(module):
    port_group_name = module.params['port_group_name']
    content = module.params['content']
    vds = module.params['vds']
    try:
        if not module.check_mode:
            port_group_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
            port_group_spec.name = port_group_name
            port_group_spec.numPorts = int(module.params['numPorts'])

            pgTypeMap = {
                'static': 'earlyBinding',
                'dynamic': 'lateBinding',
                'ephemeral': "ephemeral"
            }

            port_group_spec.type = pgTypeMap[module.params['port_binding']]

            if module.params['vlan']:
                port_group_spec.defaultPortConfig = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
                port_group_spec.defaultPortConfig.vlan = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec()
                port_group_spec.defaultPortConfig.vlan.vlanId = int(module.params['vlan'])
                port_group_spec.defaultPortConfig.vlan.inherited = False

            pg_policy = vim.dvs.DistributedVirtualPortgroup.PortgroupPolicy()
            port_group_spec.policy = pg_policy
            task = vds.AddDVPortgroup_Task(spec=[port_group_spec])
            status = task.info.state
            wait_for_task(task)
            module.exit_json(changed=True)
    except Exception, e:
        module.fail_json(msg=str(e))


def main():
    argument_spec = dict(
        hostname=dict(type='str', required=True),
        vs_port=dict(type='str'),
        username=dict(type='str', aliases=['user', 'admin'], required=True),
        password=dict(type='str', aliases=['pass', 'pwd'], required=True, no_log=True),
        vds_name=dict(type='str', required=True),
        port_group_name=dict(required=True, type='str'),
        port_binding=dict(required=True, choices=['static', 'dynamic', 'ephemeral'], type='str'),
        port_allocation=dict(choices=['fixed', 'elastic'], type='str'),
        numPorts=dict(required=True, type='str'),
        state=dict(required=True, choices=['present', 'absent'], type='str'),
        vlan=dict(type='str', required=False, default=False),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    port_group_states = {
        'absent': {
            'present': state_destroy_port_group,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_create_port_group,
        }
    }

    desired_state = module.params['state']

    si = connect.SmartConnect(host=module.params['hostname'],
                              user=module.params['username'],
                              pwd=module.params['password'],
                              port=int(module.params['vs_port']))
    if not si:
        module.fail_json(msg="Could not connect to the specified host using specified "
                             "username and password")

    content = si.RetrieveContent()
    module.params['content'] = content

    current_state = check_port_group_state(module)
    port_group_states[desired_state][current_state](module)

    connect.Disconnect(si)


from ansible.module_utils.basic import *
# from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()
