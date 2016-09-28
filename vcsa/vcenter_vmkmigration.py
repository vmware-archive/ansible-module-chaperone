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

# vmkernel adapter migrate --c
DOCUMENTATION = '''
---
module: vmware_vmkmigration
short_description: Migrate a VMK interface from VSS to VDS
description:
    - Migrate a VMK interface from VSS to VDS
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
    esxi_hostname:
        description:
            - ESXi hostname to be managed
        required: True
    device:
        description:
            - VMK interface name
        required: True
    current_switch_name:
        description:
            - Switch VMK interface is currently on
        required: True
    current_portgroup_name:
        description:
            - Portgroup name VMK interface is currently on
        required: True
    migrate_switch_name:
        description:
            - Switch name to migrate VMK interface to
        required: True
    migrate_portgroup_name:
        description:
            - Portgroup name to migrate VMK interface to
        required: True
'''

EXAMPLES = '''
Example from Ansible playbook

    - name: Migrate a VMK interface from VSS to VDS
      vcenter_vmkmigration:
        vcenter_hostname: vcsa_host
        vcenter_username: vcsa_user
        vcenter_password: vcsa_pass
        vcenter_port: vcsa_port
        esxi_hostname: esxi_hostname
        device: vmk1
        current_switch_name: temp_vswitch
        current_portgroup_name: esx-mgmt
        migrate_switch_name: dvSwitch
        migrate_portgroup_name: Management
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

def state_exit_unchanged(module):
    module.exit_json(changed=False)


def state_migrate_vds_vss(module):
    module.exit_json(changed=False, msg="Currently Not Implemented")


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

def create_host_vnic_config(dv_switch_uuid, portgroup_key, device):

    host_vnic_config = vim.host.VirtualNic.Config()
    host_vnic_config.spec = vim.host.VirtualNic.Specification()
    host_vnic_config.changeOperation = "edit"
    host_vnic_config.device = device
    host_vnic_config.portgroup = ""
    host_vnic_config.spec.distributedVirtualPort = vim.dvs.PortConnection()
    host_vnic_config.spec.distributedVirtualPort.switchUuid = dv_switch_uuid
    host_vnic_config.spec.distributedVirtualPort.portgroupKey = portgroup_key

    return host_vnic_config

def create_port_group_config(switch_name, portgroup_name):
    port_group_config = vim.host.PortGroup.Config()
    port_group_config.spec = vim.host.PortGroup.Specification()

    port_group_config.changeOperation = "remove"
    port_group_config.spec.name = portgroup_name
    port_group_config.spec.vlanId = -1
    port_group_config.spec.vswitchName = switch_name
    port_group_config.spec.policy = vim.host.NetworkPolicy()

    return port_group_config

def state_migrate_vss_vds(module):
    content = connect_to_vcenter(module);
    esxi_hostname = module.params['esxi_hostname']
    host_system = find_hostsystem_by_name(content, esxi_hostname)
    migrate_switch_name = module.params['migrate_switch_name']
    migrate_portgroup_name = module.params['migrate_portgroup_name']
    current_portgroup_name = module.params['current_portgroup_name']
    current_switch_name = module.params['current_switch_name']
    device = module.params['device']

    host_network_system = host_system.configManager.networkSystem

    dv_switch = find_dvs_by_name(content, migrate_switch_name)
    pg = find_vdspg_by_name(dv_switch, migrate_portgroup_name)

    config = vim.host.NetworkConfig()
    config.portgroup = [create_port_group_config(current_switch_name, current_portgroup_name)]
    config.vnic = [create_host_vnic_config(dv_switch.uuid, pg.key, device)]
    host_network_system.UpdateNetworkConfig(config, "modify")
    module.exit_json(changed=True)

def check_vmk_current_state(module):

    device = module.params['device']
    esxi_hostname = module.params['esxi_hostname']
    current_portgroup_name = module.params['current_portgroup_name']
    current_switch_name = module.params['current_switch_name']

    content = connect_to_vcenter(module);

    host_system = find_hostsystem_by_name(content, esxi_hostname)

    for vnic in host_system.configManager.networkSystem.networkInfo.vnic:
        if vnic.device == device:
            if vnic.spec.distributedVirtualPort is None:
                if vnic.portgroup == current_portgroup_name:
                    return "migrate_vss_vds"
            else:
                dvs = find_dvs_by_name(content, current_switch_name)
                if dvs is None:
                    return "migrated"
                if vnic.spec.distributedVirtualPort.switchUuid == dvs.uuid:
                    return "migrate_vds_vss"

def get_all_objects(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj

def find_dvs_by_name(content, vds_name):
    vdSwitches = get_all_objects(content, [vim.dvs.VmwareDistributedVirtualSwitch])
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

def find_hostsystem_by_name(content, host_name):
    host = find_vcenter_object_by_name(content, vim.HostSystem, host_name)
    if(host != ""):
        return host
    else:
        print "Host not found"
        return None

def find_vcenter_object_by_name(content, vimtype, object_name):

    vcenter_object = get_all_objects(content, [vimtype])

    for k, v in vcenter_object.items():
        if v == object_name:
            return k
    else:
        return None

def main():

    argument_spec = dict(
        vcenter_hostname=dict(type='str', required=True),
        vcenter_port=dict(type='str'),
        vcenter_username=dict(type='str', aliases=['user', 'admin'], required=True),
        vcenter_password=dict(type='str', aliases=['pass', 'pwd'], required=True, no_log=True),
        esxi_hostname=dict(required=True, type='str'),
        device=dict(required=True, type='str'),
        current_switch_name=dict(required=True, type='str'),
        current_portgroup_name=dict(required=True, type='str'),
        migrate_switch_name=dict(required=True, type='str'),
        migrate_portgroup_name=dict(required=True, type='str'))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi required for this module')

    try:
        vmk_migration_states = {
            'migrate_vss_vds': state_migrate_vss_vds,
            'migrate_vds_vss': state_migrate_vds_vss,
            'migrated': state_exit_unchanged
        }

        vmk_migration_states[check_vmk_current_state(module)](module)

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *


if __name__ == '__main__':
    main()
