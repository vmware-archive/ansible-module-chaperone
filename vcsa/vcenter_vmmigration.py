#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2015, Joseph Callen <jcallen () csc.com>
# Portions Copyright (c) 2015 VMware, Inc. All rights reserved.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: vcenter_vmmigration
short_description: Migrates a virtual machine from a standard vswitch to distributed
description:
    - Migrates a virtual machine from a standard vswitch to distributed
requirements:
    - "python >= 2.6"
    - PyVmomi
options:
    vcenter_hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    vcenter_username:
        description:
            - The username of the vSphere vCenter
        required: True
    vcenter_password:
        description:
            - The password of the vSphere vCenter
        required: True
    vcenter_port:
        description:
            - The port number of the vSphere vCenter
    vm_name:
        description:
            - Name of the virtual machine to migrate to a dvSwitch
        required: True
    dvportgroup_name:
        description:
            - Name of the portgroup to migrate to the virtual machine to
        required: True
'''

EXAMPLES = '''
- name: Migrate VM from standard vswitch to vDS
  vcenter_vmmigration:
    vcenter_hostname: vcenter_ip_or_hostname
    vcenter_username: vcenter_username
    vcenter_password: vcenter_password
    vcenter_port: vcenter_port
    vm_name: virtual_machine_name
    dvportgroup_name: distributed_portgroup_name
'''

try:
    import atexit
    import time
    import requests
    import sys
    import collections
    from pyVim import connect
    from pyVmomi import vim, vmodl

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

def connect_to_vcenter(module, disconnect_atexit=True):
    hostname = module.params['vcenter_hostname']
    username = module.params['vcenter_username']
    password = module.params['vcenter_password']
    port = module.params['vcenter_port']

    try:
        service_instance = connect.SmartConnect(
            host=hostname,
            user=username,
            pwd=password,
            port=port
        )
        if disconnect_atexit:
            atexit.register(connect.Disconnect, service_instance)
        return service_instance.RetrieveContent()
    except vim.fault.InvalidLogin, invalid_login:
        module.fail_json(msg=invalid_login.msg, apierror=str(invalid_login))
    except requests.ConnectionError, connection_error:
        module.fail_json(msg="Unable to connect to vCenter or ESXi API on TCP/443.", apierror=str(connection_error))

def get_all_objs(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj

def wait_for_task(task):
    while True:
        if task.info.state == vim.TaskInfo.State.success:
            return True, task.info.result
        if task.info.state == vim.TaskInfo.State.error:
            try:
                raise Exception(task.info.error)
            except AttributeError:
                raise Exception("An unknown error has occurred")
        if task.info.state == vim.TaskInfo.State.running:
            time.sleep(15)
        if task.info.state == vim.TaskInfo.State.queued:
            time.sleep(15)


def _find_dvspg_by_name(content, pg_name):

    vmware_distributed_port_group = get_all_objs(content, [vim.dvs.DistributedVirtualPortgroup])
    for dvspg in vmware_distributed_port_group:
        if dvspg.name == pg_name:
            return dvspg
    return None


def find_vm_by_name(content, vm_name):

    virtual_machines = get_all_objs(content, [vim.VirtualMachine])
    for vm in virtual_machines:
        if vm.name == vm_name:
            return vm
    return None


def migrate_network_adapter_vds(module):
    vm_name = module.params['vm_name']
    dvportgroup_name = module.params['dvportgroup_name']
    content = module.params['content']

    vm_configspec = vim.vm.ConfigSpec()
    nic = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
    port = vim.dvs.PortConnection()
    devicespec = vim.vm.device.VirtualDeviceSpec()

    pg = _find_dvspg_by_name(content, dvportgroup_name)

    if pg is None:
        module.fail_json(msg="The standard portgroup was not found")

    vm = find_vm_by_name(content, vm_name)
    if vm is None:
        module.fail_json(msg="The virtual machine was not found")

    dvswitch = pg.config.distributedVirtualSwitch
    port.switchUuid = dvswitch.uuid
    port.portgroupKey = pg.key
    nic.port = port

    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            devicespec.device = device
            devicespec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
            devicespec.device.backing = nic
            vm_configspec.deviceChange.append(devicespec)

    task = vm.ReconfigVM_Task(vm_configspec)
    changed, result = wait_for_task(task)
    module.exit_json(changed=changed)

def state_exit_unchanged(module):
    module.exit_json(changed=False)


def check_vm_network_state(module):
    vm_name = module.params['vm_name']
    try:
        content = connect_to_vcenter(module)
        module.params['content'] = content
        vm = find_vm_by_name(content, vm_name)
        module.params['vm'] = vm
        if vm is None:
            module.fail_json(msg="A virtual machine with name %s does not exist" % vm_name)
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                if isinstance(device.backing, vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo):
                    return 'present'
        return 'absent'
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def main():
    argument_spec = dict(
        vcenter_hostname=dict(required=True, type='str'),
        vcenter_username=dict(required=True, type='str'),
        vcenter_password=dict(required=True, type='str'),
        vcenter_port=dict(required=True, type='int'),
        vm_name=dict(required=True, type='str'),
        dvportgroup_name=dict(required=True, type='str'))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)
    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    vm_nic_states = {
        'absent': migrate_network_adapter_vds,
        'present': state_exit_unchanged,
    }

    vm_nic_states[check_vm_network_state(module)](module)

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()