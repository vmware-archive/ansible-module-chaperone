#!/usr/bin/env python
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
module: vcenter_addvmk
short_description: add vmkernel adapter to host and specified portgroup on vds
description:
    - Add vmkernel adapter to a host that has been configured on a vds
    - Assumptions: this modules assumes that the host is already configured on a vds with a management
    vmkernel adapter configured on the corresponding management portgroup
notes:
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
            - If the datacenter should be present or absent will not delete if service
            type is managment
        choices: ['present', 'absent']
        required: True
'''


EXAMPLE = '''
- name: Add vmk
  ignore_errors: no
  vcenter_addvmk:
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    esxi_hostname: '172.16.78.150'
    portgroup_name: 'vMotion Portgroup'
    dhcp: False
    ip_address: '172.16.78.99'
    subnet_mask: '255.255.255.0'
    service_type: 'vmotion'
    mtu: 1500
    state: 'present'
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


VALID_VMK_SERVICE_TYPES = [
    'faultToleranceLogging',
    'vmotion',
    'vSphereReplication',
    'vSphereReplicationNFC',
    'vSphereProvisioning',
    'vsan',
    'management',
    None
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
            return k
    else:
        return None


def get_vds_from_portgroup(module, content, portgroup_name):

    portgroup = find_vcenter_object_by_name(
        content,
        vim.dvs.DistributedVirtualPortgroup,
        portgroup_name,
    )

    if portgroup is None:
        module.fail_json(msg="Failed to find portgroup: %s" % portgroup_name)

    vds = portgroup.config.distributedVirtualSwitch

    if isinstance(vds, vim.DistributedVirtualSwitch):
        return vds
    else:
        return None


def get_portgroup_key(module, portgroup_name):
    content = module.params['content']

    portgroup = find_vcenter_object_by_name(
        content,
        vim.dvs.DistributedVirtualPortgroup,
        portgroup_name,
    )

    if portgroup.name == portgroup_name:
        return portgroup.config.key
    else:
        return None


def check_vmk_host_on_portgroup(host, portgroup_key):

    host_vnics = host.configManager.networkSystem.networkConfig.vnic

    for vnic in host_vnics:
        if vnic.spec.distributedVirtualPort is None:
            continue
        elif vnic.spec.distributedVirtualPort.portgroupKey == portgroup_key:
            return vnic
    else:
        return None


def vmkernel_adapter_spec(module):

    vdsuuid = module.params['vds_uuid']
    portgroupKey = module.params['portgroup_key']
    dhcp = module.params['dhcp']
    mtu = module.params['mtu']

    ipv6_spec = vim.host.IpConfig.IpV6AddressConfiguration(
        autoConfigurationEnabled=False,
        dhcpV6Enabled=False
    )

    if not dhcp:

        ipaddress = module.params['ip_address']
        subnetMask = module.params['subnet_mask']

        ip_spec = vim.host.IpConfig(
            dhcp=False,
            ipAddress=ipaddress,
            subnetMask=subnetMask,
            ipV6Config=ipv6_spec
        )
    else:
        ip_spec = vim.host.IpConfig(
            dhcp=True,
            ipV6Config=ipv6_spec
        )

    distrib_vport_spec = vim.dvs.PortConnection(
        switchUuid=vdsuuid,
        portgroupKey=portgroupKey
    )

    nic_spec = vim.host.VirtualNic.Specification(
        ip=ip_spec,
        distributedVirtualPort=distrib_vport_spec,
        mtu=mtu,
    )

    return nic_spec


def add_vmk_to_host(module, vmk_spec):

    host = module.params['host']

    try:
        vmk = host.configManager.networkSystem.AddVirtualNic("", vmk_spec)
    except Exception as e:
        module.fail_json(msg="Failed to add vmk adapter: %s" % str(e))

    return vmk


def get_vmk_adapter(module):

    host = module.params['host']
    portgroup_key = module.params['portgroup_key']

    host_vnics = host.configManager.networkSystem.networkConfig.vnic

    for vnic in host_vnics:
        if vnic.spec.distributedVirtualPort is None:
            continue
        elif vnic.spec.distributedVirtualPort.portgroupKey == portgroup_key:
            return vnic.device
    else:
        return None


def get_vmk_servcie_types(module):

    host = module.params['host']
    target_vmk = get_vmk_adapter(module)

    host_vmk_service_types = {
        target_vmk: []
    }

    for vmk_type in VALID_VMK_SERVICE_TYPES:
        if vmk_type is not None:
            vmks = host.configManager.virtualNicManager.QueryNetConfig(vmk_type)
            if vmks.selectedVnic:
                for vmk in vmks.candidateVnic:
                    if vmk.key in vmks.selectedVnic and vmk.device == target_vmk:
                        host_vmk_service_types[target_vmk].append(vmk_type)

    return host_vmk_service_types


def check_serviceType(module):

    vmk = get_vmk_adapter(module)
    serviceType = module.params['service_type']
    vmk_services = get_vmk_servcie_types(module)

    if not serviceType and not vmk_services[vmk]:
        return True
    elif len(vmk_services[vmk]) > 1:
        return None
    elif serviceType not in vmk_services[vmk]:
        return None
    elif serviceType in vmk_services[vmk]:
        return True


def check_vmk_networkConfig(module):

    vnic = module.params['vnic']

    if module.params['dhcp']:
        return (module.params['dhcp'] == vnic.spec.ip.dhcp)
    else:
        return (
            module.params['ip_address'] == vnic.spec.ip.ipAddress and
            module.params['subnet_mask'] == vnic.spec.ip.subnetMask and
            module.params['mtu'] == vnic.spec.mtu
        )


def check_vmk_state_spec(module):

    networkConfig_check = check_vmk_networkConfig(module)
    service_type_check = check_serviceType(module)

    if service_type_check and networkConfig_check:
        return True
    else:
        return False


def unset_vmk_service_type(module, vmk, service_type, vmk_spec):

    host = module.params['host']

    try:
        host.configManager.virtualNicManager.DeselectVnicForNicType(service_type, vmk)
    except Exception as e:
        fail_msg = "Failed to deselect service type: %s" % str(e)
        module.fail_json(msg=fail_msg)

    try:
        host.configManager.networkSystem.UpdateVirtualNic(vmk, vmk_spec)
    except Exception as e:
        module.fail_json(msg="Failed to update vnic: %s" % str(e))


def check_vmk_for_management_service(module, host):

    host_management_vmks = []

    management_vmks = host.configManager.virtualNicManager.QueryNetConfig("management")
    selected_vmk_keys = management_vmks.selectedVnic

    for vnic in management_vmks.candidateVnic:
        if vnic.key in selected_vmk_keys:
            host_management_vmks.append(vnic.device)

    return host_management_vmks


def state_delete_vmk_host(module):

    host = module.params['host']
    vmk = get_vmk_adapter(module)

    check_management_service = check_vmk_for_management_service(module, host)

    if vmk in check_management_service:
        result_msg = "vmk: %s is a management vmk and cannot be deleted" % vmk
        module.exit_json(changed=False, result=result_msg)

    remove_vmk = host.configManager.networkSystem.RemoveVirtualNic(vmk)

    if remove_vmk is None:
        result_msg = "Removed vmk: %s from host: %s" %(vmk, host.name)
    module.exit_json(changed=True, result=result_msg)


def state_update_vmk_host(module):

    host = module.params['host']
    vmk_spec = vmkernel_adapter_spec(module)
    vmk_adapter = get_vmk_adapter(module)
    vmk_service_type = module.params['service_type']
    vmk_serviceTypes = get_vmk_servcie_types(module)

    try:
        host.configManager.networkSystem.UpdateVirtualNic(vmk_adapter, vmk_spec)

        if vmk_service_type:
            for serviceType in vmk_serviceTypes[vmk_adapter]:
                if serviceType != vmk_service_type:
                    unset_vmk_service_type(module, vmk_adapter, serviceType, vmk_spec)
            host.configManager.virtualNicManager.SelectVnicForNicType(
                vmk_service_type,
                vmk_adapter
            )

        else:
            for serviceType in vmk_serviceTypes[vmk_adapter]:
                unset_vmk_service_type(module, vmk_adapter, serviceType, vmk_spec)

    except Exception as e:
        module.exit_json(msg="Failed to update vmk: {}".format(e))

    module.exit_json(changed=True, result="update vmk")


def state_create_vmk_host(module):
    host = module.params['host']
    service_type = module.params['service_type']


    vmk_spec = vmkernel_adapter_spec(module)
    vmk = add_vmk_to_host(module, vmk_spec)

    if service_type:
        host.configManager.virtualNicManager.SelectVnicForNicType(service_type, vmk)

    result_msg = "Added vmk: {} to host: {} on portgroup: {}".format(
        vmk,
        host.name,
        module.params['portgroup_name']
    )

    module.exit_json(changed=True, result=result_msg)


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="No Changes made")


def check_vmk_host_state(module):

    esxi_hostname = module.params['esxi_hostname']
    portgroup_name = module.params['portgroup_name']
    vmk_service_type = module.params['service_type']

    if vmk_service_type not in VALID_VMK_SERVICE_TYPES:
        module.fail_json(msg="Service type --> %s" % vmk_service_type)

    content = connect_to_vcenter(module)
    module.params['content'] = content

    host = find_vcenter_object_by_name(content, vim.HostSystem, esxi_hostname)

    if host is None:
        module.fail_json(msg="Esxi host: %s not in vcenter" % esxi_hostname)
    module.params['host'] = host

    vds = get_vds_from_portgroup(module, content, portgroup_name)

    if vds is None:
        module.fail_json(msg="Failed to obtain vds, vds is required")
    module.params['vds'] = vds
    module.params['vds_uuid'] = vds.uuid

    portgroup_key = get_portgroup_key(module, portgroup_name)

    if portgroup_key is None:
        module.fail_json("Failed to get the portgroup key for portgroup: %s" % portgroup_name)
    module.params['portgroup_key'] = portgroup_key

    vnic_check = check_vmk_host_on_portgroup(host, portgroup_key)

    if not vnic_check:
        return 'absent'
    else:
        module.params['vnic'] = vnic_check

        vnic_spec_check = check_vmk_state_spec(module)

        if vnic_spec_check:
            return 'present'
        else:
            return 'update'



def main():
    argument_spec = dict(
        host=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        port=dict(required=True, type='int'),
        esxi_hostname=dict(required=True, type='str'),
        portgroup_name=dict(required=True, type='str'),
        dhcp=dict(required=True, type='bool'),
        ip_address=dict(required=False, type='str'),
        subnet_mask=dict(required=False, type='str'),
        service_type=dict(default=None, required=False),
        mtu=dict(required=False, type='int', default=1500),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

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

if __name__ == '__main__':
    main()
