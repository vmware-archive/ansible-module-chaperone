#!/usr/bin/env python

DOCUMENTATION = '''
module: vcenter_addvmk
short_description: Manage VMware vSphere Datacenters
description:
    - Add vmkernel adapter to a host. Defining service type and static or
    dhcp. Module will
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
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
    esxi_hostname:
        description:
            - The password of the vSphere vCenter
        required: True
    portgroup_name:
        description:
            - The password of the vSphere vCenter
        required: True
    vmk_information:
        description:
            - The password of the vSphere vCenter
        static: bool
        vmk_ip: valid ip address for portgroup vlan or network
        vmk_subnet: valid subnet for portgroup vlan or network
        vmk_service_type: vmkernel adapter service type, see VALID_VMK_SERVICE_TYPES
                          for valid service types
        vmk_mtu: valid mtu
    state:
        description:
            - If the datacenter should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: Add vmk
  ignore_errors: no
  local_action:
    module: vcenter_addvmk
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    esxi_hostname: '172.16.78.150'
    portgroup_name: 'VIO vMotion'
    vmk_information:
      static: False
      vmk_ip: '172.16.78.99'
      vmk_subnet: '255.255.255.0'
      vmk_service_type: 'vmotion'
      vmk_mtu: 1500
    state: 'present'
  tags:
    - addvmk
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



VALID_VMK_SERVICE_TYPES = [
    'faultToleranceLogging',
    'vmotion',
    'management',
    'vSphereReplication',
    'vSphereReplicationNFC',
    'vSphereProvisioning',
    'vsan',
]

_add_vmk_serviceType = False


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


def state_exit_unchanged(module):
    module.exit_json(changed=False)


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


def check_vmk_host(module, host, portgroup_key):

    host_vnics = host.configManager.networkSystem.networkConfig.vnic

    for vnic in host_vnics:
        if vnic.spec.distributedVirtualPort.portgroupKey == portgroup_key:
            return True
    else:
        return None


def check_vmk_state_service_type(module):

    vmk_adapter_info = get_vmk_servcie_types(module)
    vmk = get_vmk_adapter(module)

    if not vmk_adapter_info[vmk]:
        global _add_vmk_serviceType
        _add_vmk_serviceType = True
        return None

    elif len(vmk_adapter_info[vmk]) > 1:
        return None

    elif module.params['vmk_service_type'] not in vmk_adapter_info[vmk]:
        return None

    elif module.params['vmk_service_type'] in vmk_adapter_info[vmk]:
        return True


def check_is_dhcp(module):
    host = module.params['host']
    vmk = get_vmk_adapter(module)

    vnics = host.configManager.virtualNicManager.info.netConfig

    for vnic in vnics:
        for candidateVnic in vnic.candidateVnic:
            if candidateVnic.device == vmk:
                if candidateVnic.spec.ip.dhcp == True:
                    return True
    else:
        return None


def check_vmk_state_ip_info(module):

    if not module.params['vmk_information']['static']:
        check_dhcp = check_is_dhcp(module)
        if check_dhcp:
            return True
        else:
            return False

    host = module.params['host']
    portgroupKey = module.params['portgroup_key']
    host_vnics = host.configManager.networkSystem.networkConfig.vnic
    ip = module.params['vmk_information']['vmk_ip']
    subnet = module.params['vmk_information']['vmk_subnet']

    check_vmk_portgroup = check_vmk_host(module, host, portgroupKey)

    if check_vmk_portgroup:
        for vnic in host_vnics:
            if (vnic.spec.ip.ipAddress == ip and vnic.spec.ip.subnetMask == subnet):
                return True
        else:
            return None

    return None


def check_vmk_for_management_service(module, host):

    host_management_vmks = []

    management_vmks = host.configManager.virtualNicManager.QueryNetConfig("management")
    selected_vmk_keys = management_vmks.selectedVnic

    for vnic in management_vmks.candidateVnic:
        if vnic.key in selected_vmk_keys:
            host_management_vmks.append(vnic.device)

    return host_management_vmks


def vmkernel_adapter_spec(module):

    vdsuuid = module.params['vds_uuid']
    portgroupKey = module.params['portgroup_key']
    static_ip = module.params['vmk_information']['static']
    mtu = module.params['vmk_information']['vmk_mtu']

    ipv6_spec = vim.host.IpConfig.IpV6AddressConfiguration(
        autoConfigurationEnabled=False,
        dhcpV6Enabled=False
    )

    if static_ip:

        ipaddress = module.params['vmk_information']['vmk_ip']
        subnetMask = module.params['vmk_information']['vmk_subnet']

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


def add_vmk_to_host(module, vmk_spec, service_type):

    host = module.params['host']

    try:
        new_vmk = host.configManager.networkSystem.AddVirtualNic("", vmk_spec)
        host.configManager.virtualNicManager.SelectVnicForNicType(service_type, new_vmk)
    except Exception as e:
        module.fail_json(msg="Failed to add vmk adapter: %s" % str(e))

    if new_vmk:
        return True
    else:
        return False


def get_vmk_adapter(module):

    host = module.params['host']
    portgroup_key = module.params['portgroup_key']

    host_vnics = host.configManager.networkSystem.networkConfig.vnic

    for vnic in host_vnics:
        if vnic.spec.distributedVirtualPort.portgroupKey == portgroup_key:
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
        vmks = host.configManager.virtualNicManager.QueryNetConfig(vmk_type)
        if vmks.selectedVnic:
            for vmk in vmks.candidateVnic:
                if vmk.key in vmks.selectedVnic and vmk.device == target_vmk:
                    host_vmk_service_types[target_vmk].append(vmk_type)

    return host_vmk_service_types


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


def state_update_vmk_host(module):

    host = module.params['host']
    service_type = module.params['vmk_service_type']

    vmk_spec = vmkernel_adapter_spec(module)
    vmk_adapter = get_vmk_adapter(module)
    vmk_serviceTypes = get_vmk_servcie_types(module)
    result_msg = "Updated vmk: %s on host: %s" % (vmk_adapter, host.name)


    try:
        host.configManager.networkSystem.UpdateVirtualNic(
            vmk_adapter,
            vmk_spec
        )

        if _add_vmk_serviceType:
            host.configManager.virtualNicManager.SelectVnicForNicType(
                service_type,
                vmk_adapter
            )
            module.exit_json(changed=True, result=result_msg)

        for serviceType in vmk_serviceTypes[vmk_adapter]:
            if serviceType != service_type:
                unset_vmk_service_type(module, vmk_adapter, serviceType, vmk_spec)

        vmk_serviceTypes = get_vmk_servcie_types(module)

        if service_type in vmk_serviceTypes[vmk_adapter]:
            if len(vmk_serviceTypes[vmk_adapter]) == 1:
                module.exit_json(changed=True, result=result_msg)
        else:
            host.configManager.virtualNicManager.SelectVnicForNicType(
                service_type,
                vmk_adapter
            )
            module.exit_json(changed=True, result=result_msg)

    except Exception as e:
        module.exit_json(msg="Failed to update vmk: %s" % str(e))


def state_create_vmk_host(module):

    vmk_spec = vmkernel_adapter_spec(module)
    service_type = module.params['vmk_service_type']

    if service_type in VALID_VMK_SERVICE_TYPES:
        vmk_service_type = service_type
    else:
        module.fail_json(msg="Invalid service type specified: %s" % service_type)

    add_vmk = add_vmk_to_host(module, vmk_spec, vmk_service_type)

    if add_vmk:
        result_msg = "Added vmkernel adapter"
        module.exit_json(changed=True, result=result_msg)
    else:
        module.fail_json(msg="Failed to add vmk to host")


def state_delete_vmk_host(module):

    host = module.params['host']
    vmk = get_vmk_adapter(module)

    check_management_service = check_vmk_for_management_service(
        module,
        host,
    )

    if vmk in check_management_service:
        result_msg = "vmk: %s is a management vmk and cannot be deleted" % vmk
        module.exit_json(changed=False, result=result_msg)

    remove_vmk = host.configManager.networkSystem.RemoveVirtualNic(vmk)

    if remove_vmk is None:
        result_msg = "Removed vmk: %s from host: %s" %(vmk, host.name)
    module.exit_json(changed=True, result=result_msg)


def check_vmk_mtu(module):

    host = module.params['host']
    mtu = module.params['vmk_information']['vmk_mtu']
    vmk = get_vmk_adapter(module)

    vnics = host.configManager.virtualNicManager.info.netConfig

    for vnic in vnics:
        for candidateVnic in vnic.candidateVnic:
            if candidateVnic.device == vmk:
                if candidateVnic.spec.mtu == mtu:
                    return True
    else:
        return None


def check_vmk_state_spec(module):
    check_serviceType = check_vmk_state_service_type(module)
    check_ip_info = check_vmk_state_ip_info(module)
    check_mtu = check_vmk_mtu(module)

    if check_serviceType and check_ip_info and check_mtu:
        return True
    else:
        return False


def check_vmk_host_state(module):

    esxi_hostname = module.params['esxi_hostname']
    portgroup_name = module.params['portgroup_name']
    vmk_service_type = module.params['vmk_information']['vmk_service_type']

    if vmk_service_type not in VALID_VMK_SERVICE_TYPES:
        module.fail_json(msg="Service type: %s NOT Valid" % vmk_service_type)
    module.params['vmk_service_type'] = vmk_service_type

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

    check_vmk_on_host = check_vmk_host(module, host, portgroup_key)

    if check_vmk_on_host is None:
        return 'absent'
    else:
        check_spec = check_vmk_state_spec(module)

        if check_spec:
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
        vmk_information=dict(required=True, type='dict'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

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
