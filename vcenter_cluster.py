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
module: vmware_cluster
short_description: Create VMware vSphere Cluster
description:
    - Create VMware vSphere Cluster according to dict spec. Module will set
    default values if only enabled specified as true. Full CRUD operations
    on specified values.
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter
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
    datacenter_name:
        description:
            - The name of the datacenter the cluster will be created in.
        required: True
    cluster_name:
        description:
            - The name of the cluster that will be created
        required: True
    ha:
        description:
            - Dict enabling HA and corresponding specifications
        required: False
        defaults: See ha_defaults
        accepted values:
          enabled: [True, False]
          admissionControlEnabled: [True, False]
          failoverLevel: [int]
          hostMonitoring: ['enabled', 'disabled']
          vmMonitoring: ['vmAndAppMonitoring', 'vmMonitoringOnly', 'vmMonitoringDisabled']
          vmMonitoring_sensitivity: [int, 0-2]
          restartPriority: ['high', 'low', 'medium', 'disabled']
    drs:
        description:
            - Dict enabling DRS and corresponding specifications.
        required: False
        defaults: See drs_defaults
        accepted values:
          enabled: [True, False]
          enableVmBehaviorOverrides: [True, False]
          defaultVmBehavior: ['fullyAutomated', 'partiallyAutomated', 'manual']
          vmotionRate: [int, 1-5]
    vsan:
        description:
            - Dict enabling VSAN and corresponding specifications.
        required: False
        accepted values:
          enabled: [True, False]
          autoClaimStorage: [True, False]
'''

EXAMPLES = '''
- name: Create Clusters
  ignore_errors: no
  vcenter_cluster:
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    datacenter_name: "{{ datacenter_name }}"
    cluster_name: "{{ item['name'] }}"
    ha:
      enabled: True
      admissionControlEnabled: True
      failoverLevel: 1
      hostMonitoring: 'enabled'
      vmMonitoring: 'vmAndAppMonitoring'
      vmMonitoring_sensitivity: 1
      restartPriority: 'high'
    drs:
      enabled: True
      enableVmBehaviorOverrides: True
      defaultVmBehavior: 'fullyAutomated'
      vmotionRate: 3
    vsan:
      enabled: True
      autoClaimStorage: True
    state: 'present'
  with_items:
    - "{{ datacenter['clusters'] }}"
  tags:
    - datacenter


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

drs_defaults = {
    'defaultVmBehavior': 'fullyAutomated',
    'vmotionRate': 3,
    'enableVmBehaviorOverrides': True
}

ha_defaults = {
    'hostMonitoring': 'enabled',
    'admissionControlEnabled': True,
    'failoverLevel': 1,
    'vmMonitoring': 'vmMonitoringDisabled'
}


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


def find_cluster_by_name_datacenter(datacenter, cluster_name):
    host_folder = datacenter.hostFolder
    for folder in host_folder.childEntity:
        if folder.name == cluster_name:
            return folder
    return None


def check_null_vals(module, spec_type):
    cluster_info = module.params[spec_type]

    if spec_type == 'drs':
        defaults = drs_defaults
    elif spec_type == 'ha':
        defaults = ha_defaults
    elif spec_type == 'vsan':
        defaults = vsan_defaults

    for k, v in cluster_info.items():
        if v == None:
            cluster_info[k] = defaults[k]


def calc_ha_values(module):
    ha_info = module.params['ha']

    ha_value = ha_info['vmMonitoring_sensitivity']

    if ha_value == 0:
        return 120, 480, 604800
    if ha_value == 1:
        return 60, 240, 86400
    if ha_value == 2:
        return 30, 120, 3600


def ha_vmSettings(module):
    ha_info = module.params['ha']
    failure_interval, min_up_time, max_fail_window = calc_ha_values(module)

    vm_tools_spec = vim.cluster.VmToolsMonitoringSettings(
        enabled=True,
        vmMonitoring=ha_info['vmMonitoring'],
        clusterSettings=True,
        failureInterval=failure_interval,
        minUpTime=min_up_time,
        maxFailures=3,
        maxFailureWindow=max_fail_window,
    )

    default_VmSettings = vim.cluster.DasVmSettings(
        restartPriority=ha_info['restartPriority'],
        isolationResponse=None,
        vmToolsMonitoringSettings=vm_tools_spec
    )

    return default_VmSettings


def configure_ha(module, enable_ha):
    check_null_vals(module, 'ha')

    ha_info = module.params['ha']
    admission_control_enabled = ha_info['admissionControlEnabled']
    failover_level = ha_info['failoverLevel']
    host_monitoring = ha_info['hostMonitoring']
    vm_monitoring = ha_info['vmMonitoring']

    if vm_monitoring in ['vmMonitoringOnly', 'vmAndAppMonitoring']:
        default_vm_settings = ha_vmSettings(module)
    else:
        default_vm_settings = None

    das_config = vim.cluster.DasConfigInfo(
        enabled=enable_ha,
        admissionControlEnabled=admission_control_enabled,
        failoverLevel=failover_level,
        hostMonitoring=host_monitoring,
        vmMonitoring=vm_monitoring,
        defaultVmSettings=default_vm_settings
    )

    return das_config


def configure_drs(module, enable_drs):
    check_null_vals(module, 'drs')

    drs_info = module.params['drs']
    drs_vmbehavior = drs_info['enableVmBehaviorOverrides']
    drs_default_vm_behavior = drs_info['defaultVmBehavior']
    drs_vmotion_rate = drs_info['vmotionRate']

    drs_spec = vim.cluster.DrsConfigInfo(
        enabled=enable_drs,
        enableVmBehaviorOverrides=drs_vmbehavior,
        defaultVmBehavior=drs_default_vm_behavior,
        vmotionRate=drs_vmotion_rate,

    )

    return drs_spec


def configure_vsan(module, enable_vsan):
    vsan_config = vim.vsan.cluster.ConfigInfo(
        enabled=enable_vsan,
        defaultConfig=vim.vsan.cluster.ConfigInfo.HostDefaultInfo(
            autoClaimStorage=module.params['vsan']['autoClaimStorage']
        )
    )

    return vsan_config


def check_spec_drs(module):
    cluster = module.params['cluster']
    drs_info = module.params['drs']
    desired_drs_spec = configure_drs(module, True)
    desired_drs_props = [prop for prop, val in desired_drs_spec._propInfo.items()]

    for i in desired_drs_props:
        val = getattr(cluster.configurationEx.drsConfig, i)
        if i != 'option':
            if val != drs_info[i]:
                return False
    else:
        return True


def check_spec_ha(module):
    cluster = module.params['cluster']
    ha_info = module.params['ha']
    desired_ha_spec = configure_ha(module, True)
    desired_ha_props = [prop for prop, val in desired_ha_spec._propInfo.items()]

    check_prop_vals = [prop for prop in ha_info.iterkeys() if prop in desired_ha_props]

    for i in check_prop_vals:
        val = getattr(cluster.configurationEx.dasConfig, i)
        if val != ha_info[i]:
            return False
    else:
        return True


def check_config_drs(module):
    cluster = module.params['cluster']
    drs_check = check_spec_drs(module)
    drs_enabled = cluster.configurationEx.drsConfig.enabled

    if drs_check and drs_enabled:
        return True
    else:
        return False


def check_config_ha(module):
    cluster = module.params['cluster']
    ha_check = check_spec_ha(module)
    ha_enabled = cluster.configurationEx.dasConfig.enabled

    if ha_check and ha_enabled:
        return True
    else:
        return False


def state_create_cluster(module):
    enable_ha = module.params['ha']['enabled']
    enable_drs = module.params['drs']['enabled']
    enable_vsan = module.params['vsan']['enabled']
    cluster_name = module.params['cluster_name']
    datacenter = module.params['datacenter']

    try:
        cluster_config_spec = vim.cluster.ConfigSpecEx()
        cluster_config_spec.dasConfig = configure_ha(module, enable_ha)
        cluster_config_spec.drsConfig = configure_drs(module, enable_drs)
        if enable_vsan:
            cluster_config_spec.vsanConfig = configure_vsan(module, enable_vsan)
        if not module.check_mode:
            datacenter.hostFolder.CreateClusterEx(cluster_name, cluster_config_spec)
        module.exit_json(changed=True)
    except vim.fault.DuplicateName:
        module.fail_json(msg="A cluster with the name %s already exists" % cluster_name)
    except vmodl.fault.InvalidArgument:
        module.fail_json(msg="Cluster configuration specification parameter is invalid")
    except vim.fault.InvalidName:
        module.fail_json(msg="%s is an invalid name for a cluster" % cluster_name)
    except vmodl.fault.NotSupported:
        module.fail_json(msg="Trying to create a cluster on an incorrect folder object")
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_destroy_cluster(module):
    cluster = module.params['cluster']
    changed = True
    result = None

    try:
        if not module.check_mode:
            task = cluster.Destroy_Task()
            changed, result = wait_for_task(task)
        module.exit_json(changed=changed, result=result)
    except vim.fault.VimFault as vim_fault:
        module.fail_json(msg=vim_fault.msg)
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_exit_unchanged(module):
    module.exit_json(changed=False)


def state_update_cluster(module):
    cluster_config_spec = vim.cluster.ConfigSpecEx()
    cluster = module.params['cluster']
    enable_ha = module.params['ha']['enabled']
    enable_drs = module.params['drs']['enabled']
    enable_vsan = module.params['vsan']['enabled']
    changed = True
    result = None

    if enable_ha:
        cluster_config_spec.dasConfig = configure_ha(module, enable_ha)
    if enable_drs:
        cluster_config_spec.drsConfig = configure_drs(module, enable_drs)
    if enable_vsan:
        cluster_config_spec.vsanConfig = configure_vsan(module, enable_vsan)

    try:
        if not module.check_mode:
            task = cluster.ReconfigureComputeResource_Task(cluster_config_spec, True)
            changed, result = wait_for_task(task)
        module.exit_json(changed=changed, result=result)
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as task_e:
        module.fail_json(msg=str(task_e))


def check_cluster_configuration(module):
    datacenter_name = module.params['datacenter_name']
    cluster_name = module.params['cluster_name']

    try:
        content = connect_to_vcenter(module)
        datacenter = find_vcenter_object_by_name(content, vim.Datacenter, datacenter_name)
        if datacenter is None:
            module.fail_json(msg="Datacenter %s does not exist" % datacenter_name)
        cluster = find_cluster_by_name_datacenter(datacenter, cluster_name)

        module.params['content'] = content
        module.params['datacenter'] = datacenter

        if cluster is None:
            return 'absent'
        else:
            module.params['cluster'] = cluster

            desired_state = (module.params['ha']['enabled'],
                             module.params['drs']['enabled'],
                             module.params['vsan']['enabled'])

            current_state = (check_config_ha(module),
                             check_config_drs(module),
                             cluster.configurationEx.vsanConfigInfo.enabled)

            if cmp(desired_state, current_state) != 0:
                return 'update'
            else:
                return 'present'
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def main():
    argument_spec = dict(
        host=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        port=dict(required=True, type='int'),
        datacenter_name=dict(required=True, type='str'),
        cluster_name=dict(required=True, type='str'),
        ha=dict(type='dict'),
        drs=dict(type='dict'),
        vsan=dict(type='dict'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    cluster_states = {
        'absent': {
            'present': state_destroy_cluster,
            'absent': state_exit_unchanged,
        },
        'present': {
            'update': state_update_cluster,
            'present': state_exit_unchanged,
            'absent': state_create_cluster,
        }
    }
    desired_state = module.params['state']
    current_state = check_cluster_configuration(module)
    cluster_states[desired_state][current_state](module)


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
