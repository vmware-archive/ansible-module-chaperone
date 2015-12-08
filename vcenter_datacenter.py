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
    - Create vcenter datacenter
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
            - The name of the datacenter the cluster will be created in.
        required: True
    state:
        description:
            - If the datacenter should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Create Datacenter
  ignore_errors: no
  vcenter_datacenter:
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    datacenter_name: "{{ datacenter_name }}"
    state: 'present'
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


def check_datacenter_state(module):
    datacenter_name = module.params['datacenter_name']

    try:
        content = connect_to_vcenter(module)
        datacenter = find_datacenter_by_name(content, datacenter_name)
        module.params['content'] = content

        if datacenter is None:
            return 'absent'
        else:
            module.params['datacenter'] = datacenter
            return 'present'
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_create_datacenter(module):
    datacenter_name = module.params['datacenter_name']
    content = module.params['content']
    changed = True
    datacenter = None

    folder = content.rootFolder

    try:
        if not module.check_mode:
            datacenter = folder.CreateDatacenter(name=datacenter_name)
        module.exit_json(changed=changed, result=str(datacenter))
    except vim.fault.DuplicateName:
        module.fail_json(msg="A datacenter with the name %s already exists" % datacenter_name)
    except vim.fault.InvalidName:
        module.fail_json(msg="%s is an invalid name for a cluster" % datacenter_name)
    except vmodl.fault.NotSupported:
        module.fail_json(msg="Trying to create a datacenter on an incorrect folder object")
    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)


def state_destroy_datacenter(module):
    datacenter = module.params['datacenter']
    changed = True
    result = None

    try:
        if not module.check_mode:
            task = datacenter.Destroy_Task()
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


def main():
    argument_spec = dict(
        host=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        port=dict(required=True, type='int'),
        datacenter_name=dict(required=True, type='str'),
        state=dict(required=True, choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    datacenter_states = {
        'absent': {
            'present': state_destroy_datacenter,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_create_datacenter,
        }
    }
    desired_state = module.params['state']
    current_state = check_datacenter_state(module)

    datacenter_states[desired_state][current_state](module)


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
