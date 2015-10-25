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

#todo check and update spec when cluster is present if needed

DOCUMENTATION = '''
creates cluster with spec values. deletes cluster if specified absent

'''

EXAMPLES = '''
- name: create cluster
  ignore_errors: no
  local_action:
    module: create_cluster
    host: '172.16.78.10'
    login: 'administrator@vsphere.local'
    password: 'VMware1!'
    port: 443
    datacenter: 'vio-dc-1'
    cluster:
      name: 'test-cluster-1'
      spec:
        DasVmSettings:
          restartPriority: 'high'
        DasConfigInfo:
          enabled: True
          admissionControlEnabled: True
          failoverLevel: 1
          hostMonitoring: 'enabled'
          vmMonitoring: 'vmAndAppMonitoring'
        DrsConfigInfo:
          enabled: True
          defaultVmBehavior: 'fullyAutomated'
        vsan:
          enabled: False
          HostDefaultInfo:
            autoClaimStorage: True
            ConfigInfo:
              enabled: True
'''

def si_connect(module):
    try:
        si = SmartConnect(host=module.params['host'],
                          user=module.params['login'],
                          pwd=module.params['password'],
                          port=module.params['port'])
    except:
        failmsg = "Could not connect to vcenter"
        module.fail_json(msg=failmsg)

    atexit.register(Disconnect, si)

    return si

def wait_for_task(task):
    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(2)
    failed = False
    if task.info.state == vim.TaskInfo.State.success:
        out = '"%s" completed successfully.%s' % \
            (task.info.task, ':%s' % task.info.result if task.info.result else '')
    else:
        failed = True
        out = '%s did not complete successfully: %s' % (task.info.task, task.info.error.msg)

    return failed, out

def get_object(module, si, vimtype, name):

    try:
        content = si.RetrieveContent()
        limit = content.rootFolder
        container = content.viewManager.CreateContainerView(limit, vimtype, True)

        if name:
            for x in container.view:
                if x.name == name:
                    return x
        else:
            return None

    except Exception as e:
        module.fail_json(msg="Failed to get id for: {} error: {}".format(name, e))

def check_cluster_present(module, si):

    try:
        cluster = get_object(module, si,
                             [vim.ClusterComputeResource],
                             module.params['cluster']['name'])
    except Exception as e:
        module.fail_json(msg="failed to check cluster: {}".format(e))

    if cluster:
        return True
    else:
        return False

def create_configspec(module):
    spec_options = module.params['cluster']['spec']
    vsan_options = spec_options['vsan']


    default_vmsettings = vim.cluster.DasVmSettings(restartPriority=spec_options['DasVmSettings']['restartPriority'])

    das_config = vim.cluster.DasConfigInfo(enabled=spec_options['DasConfigInfo']['enabled'],
                                           admissionControlEnabled=spec_options['DasConfigInfo']['admissionControlEnabled'],
                                           failoverLevel=spec_options['DasConfigInfo']['failoverLevel'],
                                           hostMonitoring=spec_options['DasConfigInfo']['hostMonitoring'],
                                           vmMonitoring=spec_options['DasConfigInfo']['vmMonitoring'],
                                           defaultVmSettings=default_vmsettings)

    drs_config = vim.cluster.DrsConfigInfo(enabled=spec_options['DrsConfigInfo']['enabled'],
                                           defaultVmBehavior=spec_options['DrsConfigInfo']['defaultVmBehavior'])

    if (vsan_options['enabled']):
        vsan_default_config = \
            vim.vsan.cluster.ConfigInfo.HostDefaultInfo(autoClaimStorage=vsan_options['HostDefaultInfo']['autoClaimStorage'])

        vsan_config = vim.vsan.cluster.ConfigInfo(enabled=vsan_options['enabled'],
                                                  defaultConfig=vsan_default_config)

        cluster_config = vim.cluster.ConfigSpecEx(dasConfig=das_config,
                                                  drsConfig=drs_config,
                                                  vsanConfig=vsan_config)
    else:
        cluster_config = vim.cluster.ConfigSpecEx(dasConfig=das_config,
                                                  drsConfig=drs_config)
    return cluster_config

def check_cluster_spec(module):
    pass

def update_cluster_spec(module):
    pass

def create_cluster(module, host_folder, cluster_name, cluster_spec):
    try:
        cluster = host_folder.CreateClusterEx(name=cluster_name, spec=cluster_spec)
    except (vim.fault.DuplicateName,
            vim.fault.InvalidName,
            vmodl.fault.InvalidArgument,
            vmodl.fault.NotSupported,
            vmodl.MethodFault) as method_fault:
        module.fail_json(msg=method_fault.msg)

    return cluster

def core(module):
    dc_name = module.params['datacenter_name']
    cluster_name = module.params['cluster']['name']

    si = si_connect(module)
    present = check_cluster_present(module, si)
    dc = get_object(module, si, [vim.Datacenter], dc_name)

    if isinstance(dc, vim.Datacenter):
        host_folder = getattr(dc, 'hostFolder')
    else:
        module.fail_json(msg="Could not get datacenter: {}".format(dc_name))

    if (module.params['state'] == 'present'):
        if not present:
            config_spec = create_configspec(module)
            cluster = create_cluster(module, host_folder, cluster_name, config_spec)

            if isinstance(cluster, vim.ClusterComputeResource):
                return False, "created cluster: {}".format(cluster.name)

        elif present:
            module.exit_json(msg="Cluster: {} is already present".format(cluster_name))

    if (module.params['state'] == 'absent'):
        if present:
            cluster = get_object(module, si, [vim.ClusterComputeResource], cluster_name)

            destroy_task = cluster.Destroy_Task()
            failed, msg = wait_for_task(destroy_task)

            return failed, msg

        else:
            module.exit_json(msg="Cluster: {} is already NOT present".format(cluster_name))



def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            state=dict(default='present', choices=['absent', 'present']),
            datacenter_name=dict(type='str'),
            cluster=dict(type='dict')
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(changed=False, msg=result)
    else:
        module.exit_json(changed=True, msg=result)


from ansible.module_utils.basic import *

if __name__ == "__main__":
    main()

