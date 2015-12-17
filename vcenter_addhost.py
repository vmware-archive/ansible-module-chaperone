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
module: vcenter_datacenter
short_description: Manage VMware vSphere Datacenters
description:
    - Add host to specified cluster
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
    datacenter_name:
        description:
            - The name of the datacenter the target cluster will be in.
        required: True
    cluster_name:
        description:
            - The name of the cluster the host will be added to.
        required: True
    esxi_hostname:
        description:
            - The esxi hostname or ip to add/remove
        required: True
    esxi_username:
        description:
            - The esx password
        required: True
    esxi_password:
        description:
            - The esx password
        required: True
    state:
        description:
            - If the datacenter should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Add Host to Clusters
  ignore_errors: no
  vcenter_addhost:
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    datacenter_name: "{{ datacenter_name }}"
    cluster_name: "{{ item.cluster }}"
    esxi_hostname: "{{ item.host }}"
    esxi_username: "root"
    esxi_password: "password"
    state: 'present'
  with_items:
    - { cluster: 'vio-edge-1', host: '172.16.78.162' }
  tags:
    - addhosts
'''

try:
    import atexit
    import time
    import requests
    import subprocess
    from pyVim import connect
    from pyVmomi import vim, vmodl
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


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
                raise Exception("An unknown error has occurred")
        if task.info.state == vim.TaskInfo.State.running:
            time.sleep(15)
        if task.info.state == vim.TaskInfo.State.queued:
            time.sleep(15)


def get_all_objs(content, vimtype):

    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj


def find_datacenter_by_name(content, datacenter_name):

    datacenters = get_all_objs(content, [vim.Datacenter])
    for dc in datacenters:
        if dc.name == datacenter_name:
            return dc

    return None


def find_cluster_by_name_datacenter(datacenter, cluster_name):

    host_folder = datacenter.hostFolder
    for folder in host_folder.childEntity:
        if folder.name == cluster_name:
            return folder
    return None


def find_host_by_cluster_datacenter(module):

    datacenter_name = module.params['datacenter_name']
    cluster_name = module.params['cluster_name']
    content = module.params['content']
    esxi_hostname = module.params['esxi_hostname']

    dc = find_datacenter_by_name(content, datacenter_name)

    if dc is None:
        module.fail_json(msg="Could not find dc: %s" % datacenter_name)
    module.params['datacenter'] = dc

    cluster = find_cluster_by_name_datacenter(dc, cluster_name)

    if cluster is None:
        module.fail_json(msg="Could not find cluster: %s" % cluster_name)
    module.params['cluster'] = cluster

    for host in cluster.host:
        if host.name == esxi_hostname:
            return host, cluster

    return None, cluster


def host_sha1(module):
    try:
        cmd_start = "echo -n | openssl s_client -connect "
        cmd_ip = module.params['esxi_hostname']
        cmd_end = ":443 2>/dev/null | openssl x509 -noout -fingerprint -sha1 | awk -F = '{print $2}'"

        cmd = cmd_start + cmd_ip + cmd_end
        output = subprocess.check_output(cmd, shell=True)
        host_sha1 = output.rstrip('\n')
        return host_sha1

    except subprocess.CalledProcessError as e:
        module.fail_json(msg=str(e))


def add_host_to_vcenter(module):
    cluster = module.params['cluster']

    host_connect_spec = vim.host.ConnectSpec()
    host_connect_spec.hostName = module.params['esxi_hostname']
    host_connect_spec.userName = module.params['esxi_username']
    host_connect_spec.password = module.params['esxi_password']
    host_connect_spec.force = True
    host_connect_spec.sslThumbprint = host_sha1(module)
    as_connected = True
    esxi_license = None
    resource_pool = None

    try:
        task = cluster.AddHost_Task(
            host_connect_spec,
            as_connected,
            resource_pool,
            esxi_license
        )

        success, result = wait_for_task(task)
        return success, result

    except Exception as e:
        module.fail_json(msg="Failed to add host: {}".format(str(e)))


def state_exit_unchanged(module):
    module.exit_json(changed=False)


def state_remove_host(module):
    host = module.params['host']
    changed = True
    result = None
    if not module.check_mode:
        if not host.runtime.inMaintenanceMode:
            maintenance_mode_task = host.EnterMaintenanceMode_Task(300, True, None)
            changed, result = wait_for_task(maintenance_mode_task)

        if changed:
            task = host.Destroy_Task()
            changed, result = wait_for_task(task)
        else:
            raise Exception(result)
    module.exit_json(changed=changed, result=str(result))


def state_update_host(module):
    module.exit_json(changed=False, msg="Currently not implemented.")


def state_add_host(module):

    changed = True
    result = None

    if not module.check_mode:
        changed, result = add_host_to_vcenter(module)
    module.exit_json(changed=changed, result=str(result))


def check_host_state(module):

    content = connect_to_vcenter(module)
    module.params['content'] = content

    host, cluster = find_host_by_cluster_datacenter(module)

    module.params['cluster'] = cluster
    if host is None:
        return 'absent'
    else:
        module.params['host'] = host
        return 'present'


def main():
    argument_spec = dict(
        host=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        port=dict(required=True, type='int'),
        datacenter_name=dict(required=True, type='str'),
        cluster_name=dict(required=True, type='str'),
        esxi_hostname=dict(required=True, type='str'),
        esxi_username=dict(required=True, type='str'),
        esxi_password=dict(required=True, type='str', no_log=True),
        state=dict(default='present', choices=['present', 'absent'], type='str')
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        host_states = {
            'absent': {
                'present': state_remove_host,
                'absent': state_exit_unchanged,
            },
            'present': {
                'present': state_exit_unchanged,
                'absent': state_add_host,
            }
        }

        host_states[module.params['state']][check_host_state(module)](module)

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
