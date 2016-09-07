#!/usr/bin/env python
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
module: vcenter_addhostdvs_assignuplink
short_description: Adds host to distributed switch and maintains physical connection
description:
    - Specifically configure an esx host to:
    add host to vds, assign uplink portgroup of dvs to the physical adapter of the added host
options:
    vcenter_hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    login:
        description:
            - The username of the vSphere vCenter
        required: True
    password:
        description:
            - The password of the vSphere vCenter
        required: True
    port:
        description:
            - The port number of the vSpherer vCenter
    datacenter_name:
        description:
            - The name of the datacenter the host will be configured in.
        required: True
    esxi_hostname:
        description:
            - The name/ip of the esx host to configure.
        required: True
    vds_name:
        description:
            - The name of the vds.
        required: True
    management_portgroup:
        description:
            - The name of the management portgroup.
        required: True
    vmnics:
        description:
            - The List of vmnics.
        required: True
    state:
        description:
            - Currently only supported is present option
        choices: ['present']
        required: True
'''

EXAMPLES = '''
- name: Adds host to distributed switch and maintains physical connection
  ignore_errors: 'true'
  vcenter_addhostdvs_assignuplink:
    vcener_hostname: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    datacenter_name: "{{ datacenter_name }}"
    esxi_hostname: "{{ item['hosts'][0]['ip'] }}"
    vds_name: "{{ vds_name }}"
    management_portgroup: "{{ management_pg_name }}"
    state: 'present'
    vmnics: ["vmnic2","vmnic2"]
  with_items:
    - "{{ datacenter['clusters'] }}"
  tags:
    - confighosts
'''

try:
    import atexit
    import time
    import requests
    import sys
    import collections
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    from pyVim import connect
    from pyVmomi import vim, vmodl

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

def connect_to_vcenter(module, disconnect_atexit=True):
    hostname = module.params['vcenter_hostname']
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
                raise Exception("An unknown error has occurred")
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


def find_dvs_uplink_pg(vds):
    if len(vds.config.uplinkPortgroup):
        return vds.config.uplinkPortgroup[0]
    else:
        return None


def find_host_attached_vds(esxi_hostname, vds):
    for vds_host_member in vds.config.host:
        if vds_host_member.config.host.name == esxi_hostname:
            return vds_host_member.config.host

    return None


def check_uplinks(module, vds, host, vmnics):
    pnic_devices = []

    for vds_host_member in vds.config.host:
        if vds_host_member.config.host == host:
            for pnicSpec in vds_host_member.config.backing.pnicSpec:
                pnic_devices.append(pnicSpec.pnicDevice)
    
    return collections.Counter(pnic_devices) == collections.Counter(vmnics)

def find_dvs_by_name(content, vds_name):
    vdSwitches = get_all_objects(content, [vim.dvs.VmwareDistributedVirtualSwitch])
    for vds in vdSwitches:
        if vds_name == vds.name:
            return vds
    return None

def find_dvs_uplink_pg(module):
        # There should only always be a single uplink port group on
        # a distributed virtual switch
    content = connect_to_vcenter(module)
    vds_name = module.params['vds_name']
    dv_switch = find_dvs_by_name(content, vds_name)
    if len(dv_switch.config.uplinkPortgroup):
        return dv_switch.config.uplinkPortgroup[0]
    else:
        return None

def modify_dvs_host(module, operation):
    content = connect_to_vcenter(module)
    vds_name = module.params['vds_name']
    esxi_hostname = module.params['esxi_hostname']
    vmnics = module.params['vmnics']
    uplink_portgroup = find_dvs_uplink_pg(module)
    dv_switch = find_dvs_by_name(content, vds_name)
    spec = vim.DistributedVirtualSwitch.ConfigSpec()
    spec.configVersion = dv_switch.config.configVersion
    spec.host = [vim.dvs.HostMember.ConfigSpec()]
    spec.host[0].operation = operation
    spec.host[0].host = find_hostsystem_by_name(content, esxi_hostname)
    if operation in ("edit", "add"):
        spec.host[0].backing = vim.dvs.HostMember.PnicBacking()
        count = 0
        for nic in vmnics:
            spec.host[0].backing.pnicSpec.append(vim.dvs.HostMember.PnicSpec())
            spec.host[0].backing.pnicSpec[count].pnicDevice = nic
            spec.host[0].backing.pnicSpec[count].uplinkPortgroupKey = uplink_portgroup.key
            count += 1

    task = dv_switch.ReconfigureDvs_Task(spec)
    changed, result = wait_for_task(task)
    return changed, result
    
def host_compatibility_check(module):
    try:
        content = connect_to_vcenter(module)
        vds_name = module.params['vds_name']
        dv_switch = find_dvs_by_name(content, vds_name)
        vds_manager = module.params['content'].dvSwitchManager
        compatible_hosts = vds_manager.QueryCompatibleHostForExistingDvs(
            module.params['datacenter'],
            True,
            dv_switch,
        )
    except Exception as e:
        module.fail_json(msg="Could not determine host compatibility: %s" % str(e))

    if module.params['host'] in compatible_hosts:
        return True
    else:
        return False


def host_migration_allowed(module):
    content = connect_to_vcenter(module)
    esxi_hostname = module.params['esxi_hostname']
    host = find_hostsystem_by_name(content, esxi_hostname)
    iscsi_manager = host.configManager.iscsiManager

    try:
        config_issue = iscsi_manager.QueryMigrationDependencies(module.params['vmnics'])
    except Exception as e:
        module.fail_json(msg="Failed to check iscsi dependencies for migration: %s" % str(e))

    return config_issue.migrationAllowed

def find_hostsystem_by_name(content, host_name):
    host = find_vcenter_object_by_name(content, vim.HostSystem, host_name)
    if(host != ""):
        return host
    else:    
        print "Host not found"
        return None

def vds_uuid(module):
    vds_switch = module.params['vds']

    if isinstance(vds_switch, vim.DistributedVirtualSwitch):
        module.params['vds_uuid'] = vds_switch.uuid
    else:
        module.fail_json(msg="Failed to get vds uuid")


def get_portgroup_key(module, portgroup_name):
    content = module.params['content']

    portgroup = find_vcenter_object_by_name(
        content,
        vim.dvs.DistributedVirtualPortgroup,
        portgroup_name,
    )

    if isinstance(portgroup, vim.dvs.DistributedVirtualPortgroup):
        return portgroup.config.key
    else:
        return None


def host_vswitch_spec_values(module):
    content = connect_to_vcenter(module)
    esxi_hostname = module.params['esxi_hostname']
    host = find_hostsystem_by_name(content, esxi_hostname)
    host_networkSystemConfig = host.configManager.networkSystem.networkConfig
    host_vswitch_name = [s.name for s in host_networkSystemConfig.vswitch][0]
    host_vswitch_numports = [n.spec.numPorts for n in host_networkSystemConfig.vswitch][0]

    module.params['host_vswitch_name'] = host_vswitch_name
    module.params['host_vswitch_numports'] = host_vswitch_numports


def host_vswitch_spec(module, change_operation):
    vswitch_numports = module.params['host_vswitch_numports']
    vswitch_name = module.params['host_vswitch_name']

    try:
        policy_shaping = vim.host.NetworkPolicy.TrafficShapingPolicy(enabled=False)

        policy_offload = vim.host.NetOffloadCapabilities(
            csumOffload=True,
            tcpSegmentation=True,
            zeroCopyXmit=True
        )

        fail_spec = vim.host.NetworkPolicy.NicFailureCriteria(
            checkSpeed="minimum",
            speed=10,
            checkDuplex=False,
            fullDuplex=False,
            checkErrorPercent=False,
            percentage=0,
            checkBeacon=False
        )

        policy_teaming = vim.host.NetworkPolicy.NicTeamingPolicy(
            policy="loadbalance_srcid",
            reversePolicy=True,
            notifySwitches=True,
            rollingOrder=False,
            failureCriteria=fail_spec
        )

        policy_sec = vim.host.NetworkPolicy.SecurityPolicy(
            allowPromiscuous=False,
            macChanges=True,
            forgedTransmits=True
        )

        vswitch_policy = vim.host.NetworkPolicy(
            security=policy_sec,
            nicTeaming=policy_teaming,
            offloadPolicy=policy_offload,
            shapingPolicy=policy_shaping
        )

        vswitch_spec = vim.host.VirtualSwitch.Specification(
            numPorts=vswitch_numports,
            policy=vswitch_policy
        )

        vswitch_config = vim.host.VirtualSwitch.Config(
            changeOperation=change_operation,
            name=vswitch_name,
            spec=vswitch_spec
        )

    except Exception as e:
        module.fail_json(msg="FAILED to build vswitch spec: %s" % str(e))

    return vswitch_config


def host_proxyswitch_spec(module, change_operation, pnic_device):
    uplink_key = module.params['uplink_portgroup_key']
    vdsuuid = module.params['vds_uuid']

    try:
        host_pnic_spec = vim.dvs.HostMember.PnicSpec(
            pnicDevice=pnic_device,
            uplinkPortgroupKey=uplink_key
        )

        host_backing = vim.dvs.HostMember.PnicBacking(pnicSpec=[host_pnic_spec])

        proxy_spec = vim.host.HostProxySwitch.Specification(backing=host_backing)

        proxy_config = vim.host.HostProxySwitch.Config(
            changeOperation=change_operation,
            uuid=vdsuuid,
            spec=proxy_spec
        )

    except Exception as e:
        module.fail_json(msg="FAILED to build host proxy switch spec: %s" % str(e))

    return proxy_config


def host_portgroup_spec(module, change_operation, portgroup_name):
    try:
        portgroup_spec_policy = vim.host.NetworkPolicy()

        portgroup_spec = vim.host.PortGroup.Specification(
            name=portgroup_name,
            vlanId=-1,
            vswitchName="",
            policy=portgroup_spec_policy
        )

        portgroup_config_spec = vim.host.PortGroup.Config(
            changeOperation=change_operation,
            spec=portgroup_spec
        )

    except Exception as e:
        module.fail_json(msg="FAILED to build host portgroup spec: %s" % str(e))

    return portgroup_config_spec


def host_vnic_spec(module, portgroup_key, change_operation, vmknic):
    vdsuuid = module.params['vds_uuid']

    try:
        vds_port_config = vim.dvs.PortConnection(
            switchUuid=vdsuuid,
            portgroupKey=portgroup_key
        )

        vnic_config_spec = vim.host.VirtualNic.Specification(
            distributedVirtualPort=vds_port_config
        )

        # change operation is edit
        vnic_config = vim.host.VirtualNic.Config(
            changeOperation=change_operation,
            device=vmknic,
            spec=vnic_config_spec
        )

    except Exception as e:
        module.fail_json(msg="FAILED to build portgroup spec %s" % str(e))

    return vnic_config


def vds_reconfigure_spec(module, change_operation):
    vds_tmp = module.params['vds']
    host_tmp = module.params['host']

    try:
        vds_spec = vim.DistributedVirtualSwitch.ConfigSpec()
        vds_spec.configVersion = vds_tmp.config.configVersion
        vds_spec_host = vim.dvs.HostMember.ConfigSpec()
        vds_spec_host.operation = change_operation
        vds_spec_host.host = host_tmp
        vds_spec.host = [vds_spec_host]

    except Exception as e:
        module.fail_json(msg="Failed to build vds reconfigure spec: %s" % str(e))

    return vds_spec


def build_vswitch_spec(module):
    operation = "edit"
    host_vswitch_spec_values(module)
    vswitch_spec = host_vswitch_spec(module, operation)

    return vswitch_spec


def build_proxy_spec(module):
    operation = "edit"
    pnic = module.params['vmnics'][0]
    proxy_spec = host_proxyswitch_spec(module, operation, pnic)

    return proxy_spec


def build_portgroup_spec(module):
    operation = "remove"
    pg_name = "Management Network"
    portgroup_spec = host_portgroup_spec(module, operation, pg_name)

    return portgroup_spec


def get_management_vmk(module):

    content = connect_to_vcenter(module)
    esxi_hostname = module.params['esxi_hostname']
    host = find_hostsystem_by_name(content, esxi_hostname)

    try:
        net_config= host.configManager.virtualNicManager.QueryNetConfig("management")
    except Exception as e:
        module.fail_json(msg="Failed to get vmk: {}".format(str(e)))

    for vmk in net_config.candidateVnic:
        if vmk.portgroup == "Management Network":
            return vmk.device
    else:
        return None


def build_vnic_spec(module):
    pg_name = module.params['management_portgroup']
    pg_key = get_portgroup_key(module, pg_name)
    operation = "edit"
    vmk = get_management_vmk(module)

    if vmk is None:
        module.fail_json(msg="Could not obtain management vmkernel adapter")

    if pg_key:
        vnic_spec = host_vnic_spec(module, pg_key, operation, vmk)
        return vnic_spec
    else:
        module.fail_json(msg="Failed to get pg key")


def build_hostnetworkconfig(module):
    vswitch_spec = build_vswitch_spec(module)
    proxy_spec = build_proxy_spec(module)
    portgroup_spec = build_portgroup_spec(module)
    vnic_spec = build_vnic_spec(module)

    host_network_config_spec = vim.host.NetworkConfig(
        vswitch=[vswitch_spec],
        proxySwitch=[proxy_spec],
        portgroup=[portgroup_spec],
        vnic=[vnic_spec]
    )

    return host_network_config_spec


def host_remove_vswitch(module):
    content = connect_to_vcenter(module)
    esxi_hostname = module.params['esxi_hostname']
    host = find_hostsystem_by_name(content, esxi_hostname)
    host_networkSystem = host.configManager.networkSystem
    vswitch = host_networkSystem.networkInfo.vswitch[0].name

    try:
        remove_vswitch = host_networkSystem.RemoveVirtualSwitch(vswitch)
    except (vim.fault.NotFound,
            vim.fault.ResourceInUse,
            vim.fault.HostConfigFault) as vim_fault:
        module.fail_json(msg="Failed to remove: %s with error: %s" % (vswitch, vim_fault))

    if remove_vswitch is None:
        return True
    else:
        return False


def reconfigure_vds_task(module, vds, reconfig_spec):
    try:
        reconfigure_task = vds.ReconfigureDvs_Task(reconfig_spec)
        changed, result = wait_for_task(reconfigure_task)
    except Exception as e:
        module.fail_json(msg="Failed to reconfigure vds with host: %s" % str(e))

    return changed, result


def state_update_vds_host(module):
    operation = "edit"
    changed = True
    result = None

    if not module.check_mode:
        changed, result = modify_dvs_host(module, operation)
        return changed,result

def state_destroy_vds_host(module):
    module.exit_json(changed=False, result="Currently not supported", msg="Inside destroy vds host")


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="Inside state exit unchanged")


def state_create_vds_host(module):
    vds_task_operation = "add"
    vds = module.params['vds']
    host = module.params['host']

    compatible = host_compatibility_check(module)
    migration_allowed = host_migration_allowed(module)

    if compatible and migration_allowed:
        host_network_spec = build_hostnetworkconfig(module)
        vds_reconfig_spec_task = vds_reconfigure_spec(module, vds_task_operation)

        changed, result = reconfigure_vds_task(module, vds, vds_reconfig_spec_task)
    else:
        fail_msg = "Host: %s is not compatible or has migration issues" % host.name
        module.fail_json(msg=fail_msg)

    if changed:
        try:
            host.configManager.networkSystem.UpdateNetworkConfig(
                host_network_spec,
                "modify"
            )
        except Exception as e:
            module.fail_json(msg="Failed to add host to vds and configure: %s" % e)

    else:
        fail_msg = "Failed to add the host: %s to vds: %s" % (host.name, vds.name)
        module.fail_json(msg=fail_msg)


def check_vds_host_state(module):
    datacenter_name = module.params['datacenter_name']
    vds_name = module.params['vds_name']
    esxi_hostname = module.params['esxi_hostname']
    vmnics = module.params['vmnics']

    content = connect_to_vcenter(module)
    module.params['content'] = content
    datacenter = find_vcenter_object_by_name(content, vim.Datacenter, datacenter_name)

    if datacenter is None:
        module.fail_json(msg="Cannot find specificed datacenter: %s" % datacenter_name)
        
    vds = find_vcenter_object_by_name(content, vim.DistributedVirtualSwitch, vds_name)

    if vds is None:
        module.fail_json(msg="Virtual distributed switch: %s does not exist" % vds_name)

    uplink_portgroup = find_dvs_uplink_pg(module)

    if uplink_portgroup is None:
        module.fail_json(msg="An uplink portgroup does not exist on the distributed virtual switch %s" % vds_name)
    
    module.params['datacenter'] = datacenter
    module.params['vds'] = vds
    module.params['vds_uuid'] = vds.uuid
    module.params['uplink_portgroup'] = uplink_portgroup
    module.params['uplink_portgroup_key'] = uplink_portgroup.key
    
    host = find_host_attached_vds(esxi_hostname, vds)
    if host is None:
        host = find_vcenter_object_by_name(content, vim.HostSystem, esxi_hostname)
        if host is None:
            module.fail_json(msg="Esxi host: %s not in vcenter" % esxi_hostname)
        module.params['host'] = host
        return 'absent'
    else:
        module.params['host'] = host
        if check_uplinks(module, vds, host, vmnics):
            return 'present'
        else:
            return 'update'

def main():
    argument_spec = dict(
        vcenter_hostname=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        port=dict(type='int'),
        datacenter_name=dict(required=True, type='str'),
        esxi_hostname=dict(required=True, type='str'),
        vds_name=dict(required=True, type='str'),
        management_portgroup=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
        vmnics=dict(required=True, type='list'))

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:

        dvs_host_states = {
            'absent': {
                'present': state_destroy_vds_host,
                'absent': state_exit_unchanged,
            },
            'present': {
                'update': state_update_vds_host,
                'present': state_exit_unchanged,
                'absent': state_create_vds_host,
            }
        }

        dvs_host_states[module.params['state']][check_vds_host_state(module)](module)

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()