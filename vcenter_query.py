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

DOCUMENTATION = '''
---
module: vcenter_query
Short_description: Query vCenter for inventory id by inventory name and return custom fact
description:
    - Provides an interface to query vcenter, return id as specified custom fact
versoin_added: "0.1"
options:
    host:
    resourcename:
        description:
            - vCenter inventory object name target
        required: True
        default: Null
    resourcevarname:
        description:
            - Valid Ansible variable name for custom fact setting to returned id
        required: True
        default: Null
    resourcetype:
        description:
            - vCenter resource type valid options are
            - cluster, datacenter, datastore, dvs, dvs-port, vm
        required: True
        default: Null
'''
EXAMPLES = '''
- name: Get vCenter ID
  ignore_errors: no
  local_action:
    module: vcenter_query
    host: vcenter_host
    login: vcenter_user
    password: vcenter_password
    port: vcenter_port
    resourcename: "{{ vio_cluster_mgmt }}"
    resourcevarname: 'your_var_name'
    resourcetype: 'cluster'

- name: test new custom var
  shell: /bin/echo "{{ your_var_name }}"
'''

class Getnamesids(object):

    def __init__(self, module):
       self.module = module
       self.vsphere_host = module.params.get('host')
       login_user = module.params.get('login')
       login_password = module.params.get('password')
       self.port = module.params.get('port')

       try:
           self.si = SmartConnect(host=self.vsphere_host, user=login_user, pwd=login_password, port=self.port)
       except:
           failmsg = "Could not connect to virtualserver: %s with: %s %s" \
                     % (self.vsphere_host, login_user, login_password)
           self.module.fail_json(msg=failmsg)

       atexit.register(Disconnect, self.si)

    @property
    def content(self):
        if not hasattr(self, '_content'):
            self._content = self.si.RetrieveContent()
        return self._content

    def get_target_object(self, vimtype, name, getobject=None, moid=None):
        '''
        :param vimtype: valid vim type
        :param name: name of the target (module.params.get('resourcename'))
        :param getobject: specify True if wanting to return the target object
        :param moid: specify True if wanting to return the moId property
        :param return: will return None if name is not found, or the object, or the moId of target
        '''
        limit = self.content.rootFolder
        container = self.content.viewManager.CreateContainerView(limit, vimtype, True)

        if name:
            for x in container.view:
                if x.name == name:
                    if moid:
                        return str(x._moId)
                    if getobject:
                        return x
        else:
            fail_msg = "Please enter a valid name"
            self.module.fail_json(msg=fail_msg)

    
def core(module):

    rec_name = module.params.get('resourcename')
    rec_type = module.params.get('resourcetype')

    vim_rec_type = {
        'cluster': vim.ClusterComputeResource,
        'datacenter': vim.Datacenter,
        'datastore': vim.Datastore,
        'vds': vim.DistributedVirtualSwitch,
        'dvs-port': vim.Network,
        'vm': vim.VirtualMachine
    }

    names_ids = Getnamesids(module)
    
    try:
        vim_type = vim_rec_type[rec_type]
    except KeyError:
        fail_msg = "resourcetype not Valid, Valid: cluster, datacenter, datastore, vds, vm"
        module.fail_json(msg=fail_msg)
        
    object_id = names_ids.get_target_object([vim_type], rec_name, None, True)
        
    if object_id:
        return False, object_id
    else:
        msg = "FAILED: %s" % object_id
        return True, msg


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            resourcename=dict(type='str', required=True),
            resourcevarname=dict(type='str', required=True),
            resourcetype=dict(type='str', required=True),
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(msg=result)
    else:
        ansible_facts_dict = {
            "changed": False,
            "ansible_facts": {

            }
        }

        resource_id = result
        resource_var = module.params.get('resourcevarname')
        ansible_facts_dict['ansible_facts'].update({resource_var: resource_id})
        ansible_facts_dict['changed'] = True
        print json.dumps(ansible_facts_dict)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()

