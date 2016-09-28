#!/usr/bin/python
#
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
module: vcenter_addvmk
short_description: add vmkernel adapter to host and specified portgroup on vds
description:
    - Add vmkernel adapter to a host that has been configured on a vds
    - Assumptions: this modules assumes that the host is already configured on a vds with a management
    vmkernel adapter configured on the corresponding management portgroup
notes:
    requirements: ansible 2.x
    - Tested on vSphere 6.0
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    username:
        description:
            - The username of the vSphere vCenter
        required: True
    password:
        description:
            - The password of the vSphere vCenter
        required: True
    esxi_hostname:
        description:
            - The hostname or ip of the esxi host to add the vmkernel adapter
        required: True
    portgroup_name:
        description:
            - The name of the portgroup to add the vmkernel adapter to
        required: True
    dhcp:
        description:
            - Specify if you require dhcp or static addressing
        required: True
        choices: [True, False]
    ip_address:
        description:
            - Specify the ip address if dhcp is set to True
        required: False
    subnet_mask:
        description:
            - Specify the subnet mask if dhsp is set to True
        required: False
    service_type:
        description:
            - Specify the valid service type if left blank the service type will be None and no service type will be specified
        required: False
        choices: [
            'faultToleranceLogging',
            'vmotion',
            'vSphereReplication',
            'vSphereReplicationNFC',
            'vSphereProvisioning',
            'vsan',
            'management',
        ]
        default: None
    mtu:
        description:
            - Specify the mtu
        type: int
        required: False
        default: 1500
    state:
        description:
            - present or absent
            type is managment
        choices: ['present', 'absent']
        required: True
'''


EXAMPLE = '''
- name: Add vmkernel adapter to host on specified portgroup
  vcenter_addvmk:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    esxi_hostname: "{{ item.name }}"
    portgroup_name: "{{ item.pg_name }}"
    dhcp: "{{ item.dhcp }}"
    ip_address: "{{ item.ipaddr }}"
    subnet_mask: "{{ item.subnet }}"
    service_type: "{{ item.servicetype }}"
    mtu: "{{ item.mtu }}"
    state: "{{ global_state }}"
  with_items:
    - "{{ vcenter_host_pgs }}"
  tags:
    - addvmk
'''


try:
    import atexit
    import time
    import requests
    from pyVim import connect
    from pyVmomi import vim, vmodl

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


vc = {}


VALID_VMK_SERVICE_TYPES = [
    'faultToleranceLogging',
    'vmotion',
    'vSphereReplication',
    'vSphereReplicationNFC',
    'vSphereProvisioning',
    'vsan',
    'management',
    None,
]


def connect_to_vcenter(module, disconnect_atexit=True):
    hostname = module.params['host']
    username = module.params['login']
    password = module.params['password']
    port = module.params['port']

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

def find_hostsystem_by_name(content, host_name):
    host = find_vcenter_object_by_name(content, vim.HostSystem, host_name)
    if(host != ""):
        return host
    else:
        print "Host not found"
        return None

def find_vcenter_object_by_name(content, vimtype, object_name):

    vcenter_object = get_all_objs(content, [vimtype])

    for k, v in vcenter_object.items():
        if v == object_name:
            return k
    else:
        return None

def get_all_objs(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj

def get_host_vmk():

    vmk = None

    host = vc['host']
    portgroup_key = vc['portgroup_key']

    vnics = [v for v in host.config.network.vnic if v.spec.distributedVirtualPort]

    if not vnics:
        return vmk

    for vnic in vnics:
        if vnic.spec.distributedVirtualPort.portgroupKey == portgroup_key:
            vmk = vnic

    return vmk


def check_vmk_net_config(module, vmk):

    state = False

    vmk_ip = vmk.spec.ip.ipAddress
    vmk_subnet = vmk.spec.ip.subnetMask

    if not (vmk.spec.mtu == module.params['mtu']):
        return state

    dhcp = vmk.spec.ip.dhcp

    if not (dhcp == module.params['dhcp']):
        return state

    if not module.params['dhcp']:
        if (vmk_ip == module.params['ip_address']) and (vmk_subnet == module.params['subnet_mask']):
            state = True
    elif module.params['dhcp']:
        state = True

    return state


def _query_vmk_service_type(module, service_type):

    query_result = None
    host = vc['host']

    try:
        query_result = host.configManager.virtualNicManager.QueryNetConfig(service_type)
    except vim.fault.HostConfigFault as config_fault:
        module.fail_json(msg="Failed check vmk service type config fault: {}".format(str(config_fault)))
    except vmodl.fault.InvalidArgument as invalid_arg:
        module.fail_json(msg="Failed check vmk service type invalid arg: {}".format(str(invalid_arg)))
    except Exception as e:
        module.fail_json(msg="Failed check vmk service type: {}".format(str(e)))

    return query_result


def _get_list_vmk_with_servicetype(query_result):

    if not query_result.selectedVnic:
        return None

    selected_vmks = [i for i in query_result.selectedVnic]

    vmks_with_servicetype = [v.device for v in query_result.candidateVnic if v.key in selected_vmks]

    return vmks_with_servicetype


def check_vmk_service_type(module):

    vmk = vc['vmk']
    desired_service_type = module.params['service_type']
    servicetype_vmk = {}

    for service_type in VALID_VMK_SERVICE_TYPES:
        if service_type:
            query = _query_vmk_service_type(module, service_type)
            vmk_list = _get_list_vmk_with_servicetype(query)
            servicetype_vmk.update({service_type:vmk_list})

    vmk_servicetype_list = []

    for k, v in servicetype_vmk.items():
        if v:
            if vmk.device in v:
                vmk_servicetype_list.append(k)

    if not vmk_servicetype_list and not desired_service_type:
        return True, None

    if not (desired_service_type in vmk_servicetype_list):
        return False, vmk_servicetype_list

    if len(vmk_servicetype_list) > 1:
        vmk_servicetype_list.remove(desired_service_type)
        return False, vmk_servicetype_list

    return True, None


def vmk_spec(module):

    vdsuuid = vc['vds_uuid']
    portgroupKey = vc['portgroup_key']
    dhcp = module.params['dhcp']
    mtu = module.params['mtu']

    if not dhcp:

        ipaddress = module.params['ip_address']
        subnetMask = module.params['subnet_mask']

        ip_spec = vim.host.IpConfig(dhcp=False,
                                    ipAddress=ipaddress,
                                    subnetMask=subnetMask)
    else:
        ip_spec = vim.host.IpConfig(dhcp=True)

    distrib_vport_spec = vim.dvs.PortConnection(switchUuid=vdsuuid,
                                                portgroupKey=portgroupKey)

    nic_spec = vim.host.VirtualNic.Specification(ip=ip_spec,
                                                 distributedVirtualPort=distrib_vport_spec,
                                                mtu=mtu)

    return nic_spec


def add_vmk_to_host(module):

    vmkdevice = None

    host = vc['host']
    vnic_spec = vmk_spec(module)

    try:
        vmkdevice = host.configManager.networkSystem.AddVirtualNic("", vnic_spec)
    except vim.fault.AlreadyExists as present:
        module.exit_json(changed=False, result=str(present))
    except vim.fault.HostConfigFault as config_fault:
        module.fail_json(msg="Failed adding vmk config issue: {}".format(str(config_fault)))
    except vim.fault.InvalidState as invalid_state:
        fail_msg ="Failed adding vmk ipv6 address is specified in an ipv4 only system: {}".format(str(invalid_state))
        module.fail_json(msg=fail_msg)
    except vmodl.fault.InvalidArgument as invalid_arg:
        fail_msg = "Failed adding vmk P address or subnet mask in the IP configuration are invalid" \
                   "or PortGroup does not exist".format(str(invalid_arg))
        module.fail_json(msg=fail_msg)
    except Exception as e:
        module.fail_json(msg="Failed adding vmk general error: {}".format(str(e)))

    return vmkdevice


def set_vmk_service_type(module, vmk):
    state = False
    service_type = module.params['service_type']
    host = vc['host']

    try:
        host.configManager.virtualNicManager.SelectVnicForNicType(service_type, vmk)
        state = True
    except vmodl.fault.InvalidArgument as invalid_arg:
        fail_msg = "Failed setting vmk service type" \
                   "nicType is invalid, or device represents" \
                   " a nonexistent or invalid VirtualNic: {}".format(str(invalid_arg))
        module.fail_json(msg=fail_msg)
    except Exception as e:
        module.fail_json(msg="Failed setting vmk service type: {}".format(str(e)))

    return state


def vsan_spec(vmk):

    vsan_port = vim.vsan.host.ConfigInfo.NetworkInfo.PortConfig(device=vmk)
    net_info = vim.vsan.host.ConfigInfo.NetworkInfo(port=[vsan_port])
    vsan_config = vim.vsan.host.ConfigInfo(networkInfo=net_info)

    return vsan_config


def set_vmk_service_type_vsan(module, vmk):

    changed = False
    result = None

    host = vc['host']
    vsan_system = host.configManager.vsanSystem

    vsan_config = vsan_spec(vmk)

    try:
        vsan_task = vsan_system.UpdateVsan_Task(vsan_config)
        changed, result = wait_for_task(vsan_task)
    except Exception as e:
        module.fail_json(msg="Failed to set service type to vsan: {}".format(str(e)))

    return changed, result

def wait_for_task(task):
    while True:
        if task.info.state == vim.TaskInfo.State.success:
            return True, task.info.result
        if task.info.state == vim.TaskInfo.State.error:
            try:
                raise Exception(task.info.error)
            except AttributeError:
                raise TaskError("An unknown error has occurred")
        if task.info.state == vim.TaskInfo.State.running:
            time.sleep(15)
        if task.info.state == vim.TaskInfo.State.queued:
            time.sleep(15)

def state_create_vmk_host(module):

    changed = False
    result = []

    vmk_added = add_vmk_to_host(module)

    if vmk_added:
        changed = True
        result.append(vmk_added)

    if module.params['service_type'] == 'vsan':
        set_servicetype_changed, set_servicetype_result = set_vmk_service_type_vsan(module, vmk_added)
        changed = True
        result.append(set_servicetype_result)
    elif module.params['service_type']:
        set_servicetype = set_vmk_service_type(module, vmk_added)
        result.append(set_servicetype)

    module.exit_json(changed=changed, result=result)


def state_update_vmk_host(module):

    changed = False
    result = None

    host = vc['host']
    vmk = vc['vmk']
    service_type = module.params['service_type']

    if not vc['update_servicetype']:

        for i in vc['unset_list']:

            try:
                host.configManager.virtualNicManager.DeselectVnicForNicType(i, vmk.device)
            except Exception as e:
                module.fail_json(msg="Failed to deselect vmk: {} for service: {} error: {}".format(vmk.device, i, str(e)))

        if service_type == 'vsan':
            changed, result = set_vmk_service_type_vsan(module, vmk.device)
        elif service_type:
            changed = set_vmk_service_type(module, vmk.device)
            result = vmk.device

    if not vc['update_netconfig']:

        spec = vmk_spec(module)
        try:
            host.configManager.networkSystem.UpdateVirtualNic(vmk.device, spec)
        except Exception as e:
            module.fail_json(msg="Failed to update network config for vmk: {} error: {}".format(vmk.device, str(e)))

    module.exit_json(changed=changed, result=result)


def state_delete_vmk_host(module):
    module.exit_json(changed=False, msg="STATE DELETE")


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def check_vmk_host_state(module):

    state = 'absent'

    esxi_hostname = module.params['esxi_hostname']
    vmk_service_type = module.params['service_type']
    portgroup_name = module.params['portgroup_name']

    if vmk_service_type not in VALID_VMK_SERVICE_TYPES:
        module.params['service_type'] = None

    #si = connect_to_api(module)
    si = connect_to_vcenter(module)
    vc['si'] = si

    host = find_hostsystem_by_name(si, esxi_hostname)

    if host is None:
        module.fail_json(msg="Esxi host: {} not found".format(esxi_hostname))

    vc['host'] = host

    portgroup = find_vcenter_object_by_name(si, vim.dvs.DistributedVirtualPortgroup, portgroup_name)

    if not portgroup:
        module.fail_json(msg="Could not find portgroup specified: {}".format(portgroup_name))

    vc['portgroup'] = portgroup
    vc['portgroup_key'] = portgroup.config.key
    vc['vds_uuid'] = portgroup.config.distributedVirtualSwitch.uuid

    vmk = get_host_vmk()

    if not vmk:
        return state

    vc['vmk'] = vmk

    vmk_net_config = check_vmk_net_config(module, vmk)
    service_type_check, unset_list = check_vmk_service_type(module)

    vc['unset_list'] = unset_list

    if not vmk_net_config or not service_type_check:

        vc['update_netconfig'] = vmk_net_config
        vc['update_servicetype'] = service_type_check

        state = 'update'
    else:
        state = 'present'

    return state


def main():
    #argument_spec = vmware_argument_spec()

    argument_spec=dict(
            host=dict(required=True, type='str'),
            login=dict(required=True, type='str'),
            password=dict(required=True, type='str'),
            port=dict(required=True, type='int'),
            esxi_hostname=dict(required=True, type='str'),
            portgroup_name=dict(required=True, type='str'),
            dhcp=dict(required=True, type='bool'),
            ip_address=dict(required=False, type='str'),
            subnet_mask=dict(required=False, type='str'),
            service_type=dict(default=None, required=False, type='str'),
            mtu=dict(required=False, type='int', default=1500),
            state=dict(default='present', choices=['present', 'absent'], type='str'))


    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        vmk_host_states = {
            'absent': {
                'update': state_delete_vmk_host,
                'present': state_delete_vmk_host,
                'absent': state_exit_unchanged,
            },
            'present': {
                'update': state_update_vmk_host,
                'present': state_exit_unchanged,
                'absent': state_create_vmk_host,
            }
        }

        vmk_host_states[module.params['state']][check_vmk_host_state(module)](module)

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *
#from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()