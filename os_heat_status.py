#!/usr/bin/python
# coding=utf-8
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

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: vio_check_heat_stack
Short_description: Checks if heat stack is present and deletes if heat stack is in given state
description:
    Module will check if a heat stack is present for a specified tenant. If the heat stack is in
    the following states DELETE_FAILED, CREATE_COMPLETE, CREATE_FAILED
    Module will delete the heat stack. Module specifically developed for the ansible-role-vio
requirements:
    - keystoneclient.v2_0
    - requests
    - urlparse
Tested on:
    - vio 2.5
    - ansible 2.1.2
version_added: 2.2
author: VMware
options:
    auth_url:
        description:
            - keystone authentication for the openstack api endpoint
        required: True
    username:
        description:
            - user with rights to specified project
        required: True
    password:
        description:
            - password for specified user
        required: True
    tenant_name:
        description:
            - tenant name with authorization for specified project
        required: True
'''

EXAMPLES = '''
- name: Check Heat stack present
  vio_check_heat_stack:
    auth_url: "https://{{ vio_loadbalancer_vip }}:5000/v2.0"
    username: "{{ projectuser }}"
    password: "{{ projectpass }}"
    tenant_name: "{{ vio_val_project_name }}"
    heat_stack_name: "{{ vio_val_heat_name }}"
  register: stack_present
  tags:
    - validate_openstack
'''

RETURN = '''
description: Returns an empty list if there are no stacks present or a list of stacks deleted
returned:
type:
sample:
'''


try:
    from keystoneclient.v2_0 import client as ks_client
    from urlparse import urlparse
    import requests
    import time
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False

def keystone_auth(module):
    ksclient = None
    try:
        ksclient = ks_client.Client(username=module.params['username'],
                                    password=module.params['password'],
                                    tenant_name=module.params['project_name'],
                                    auth_url=module.params['auth_url'],
                                    insecure=True)
    except Exception as e:
        module.fail_json(msg="Failed to get keystone client authentication: {}".format(e))
    return ksclient

def stack_get(module, heaturl, token, status_code):
    rheaders = {'X-Auth-Token': "%s" % token}
    resp = requests.get(heaturl, headers=rheaders, verify=False)

    if resp.status_code != status_code:
        module.fail_json(msg="Failed to get stack status: {}".format(resp.status_code))

    content = resp.json()
    return content

def stack_delete(module, heaturl, token, status_code):

    rheaders = {'X-Auth-Token': "%s" % token}
    resp = requests.delete(heaturl, headers=rheaders, verify=False)

    if resp.status_code != status_code:
        module.fail_json(msg="Failed to get stack status: {}".format(resp.status_code))

    return resp.status_code


def project_stacks(module, token, endpoint, project_id):
    url = 'https://{}:8004/v1/{}/stacks'.format(endpoint, project_id)
    content = stack_get(module, url, token, 200)
    return content['stacks']

def stack_status(module, token, endpoint, project_id, stack_data):
    stack_name = stack_data['stack_name']
    stack_id = stack_data['id']
    url = 'https://{}:8004/v1/{}/stacks/{}/{}'.format(endpoint, project_id, stack_name, stack_id)
    content = stack_get(module, url, token, 200)
    return content['stack']['stack_status']

def wait_for_stack(module, token, endpoint, project_id):
    stack_info = []
    url = 'https://{}:8004/v1/{}/stacks'.format(endpoint, project_id)
    del_url = '{}/{}/{}'

    stacks = project_stacks(module, token, endpoint, project_id)

    if not stacks:
        return stack_info

    for stack in stacks:
        stack_delete_url = del_url.format(url, stack['stack_name'], stack['id'])
        wait_count = 0

        while wait_count < 21:
            project_stack_status = project_stacks(module, token, endpoint, project_id)

            if not project_stack_status:
                break

            status = stack_status(module, token, endpoint, project_id, stack)
            stack_data = {'name': stack['name'], 'status': status}

            if status == "CREATE_COMPLETE" or status == "CREATE_FAILED":
                delete_status = stack_delete(module, stack_delete_url, token, 204)
                stack_info.append(stack_data)

            elif status == "DELETE_IN_PROGRESS":
                stack_data.update({'status': status})
                stack_info.append(stack_data)

                wait_count += 1
                time.sleep(45)

            elif status == "DELETE_FAILED":

                delete_status = stack_delete(module, stack_delete_url, token, 204)

                if not (delete_status == 204):
                    msg = "Failed to Delete Stack: {} with STATUS - {}".format(stack['stack_name'], delete_status)
                    module.fail_json(msg=msg)
                elif delete_status == 204:
                    break

            else:
                wait_count += 1
                time.sleep(20)

            if wait_count == 21:
                break

    return stack_info


def main():

    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        username=dict(required=True, type='str'),
        password=dict(required=True, type='str', no_log=True),
        project_name=dict(required=True, type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_CLIENTS:
        module.fail_json(msg='python-requests is required for this module')

    changed = False

    ks = keystone_auth(module)
    token = ks.auth_token
    project_id = ks.tenant_id
    vioendpoint = urlparse(module.params['auth_url']).netloc.split(':')[0]

    project_stack_info = wait_for_stack(module, token, vioendpoint, project_id)

    if project_stack_info:
        changed=True

    module.exit_json(changed=changed, stack_data_info=project_stack_info)


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
