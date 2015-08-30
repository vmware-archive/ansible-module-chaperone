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

import ssl
if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
except ImportError:
    print("failed=True msg='pyVmomi is required to run this module'")

EXAMPLES = '''
- name: Get Management Cluster Resource Group Object ID
  ignore_errors: no
  local_action:
    module: get_cluster_resgroup
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    cluster: "{{ vio_cluster_mgmt }}"
    resourcevarname: 'vio_cluster_mgmt_resgroup'
'''

class Getresgroupvms(object):
    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except:
            creds = vhost + " " + user + " " + password
            self.module.fail_json(msg='Could not connect to: %s' % creds)
        return self.SI

    def get_content(self, connection):
        try:
            content = connection.RetrieveContent()
        except Exception as e:
            return str(e)
        return content

    def get_target_object(self, connection, vimtype, target_name):
        try:
            content = self.get_content(connection)
            vc_object = {}
            container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
            for managed_object_ref in container.view:
                vc_object.update({managed_object_ref.name: managed_object_ref})
            if target_name in vc_object:
                for k, v in vc_object.items():
                    if k == target_name:
                        failed = False
                        target = v
                        return failed, target
            else:
                failed = True
                failmsg = "Target Cluster--> %s Not Found" % target_name
                return failed, dict(msg=failmsg)
        except vmodl.MethodFault as method_fault:
            return True, dict(msg=method_fault.msg)
        except vmodl.RuntimeFault as runtime_fault:
            return True, dict(msg=runtime_fault.msg)

    def get_resourcepool_id(self, targetcluster_object):
        try:
            cluster = targetcluster_object
            resource_group = cluster.resourcePool
            resource_group_id = str(resource_group).split(':')[1].replace("'", "")
            return resource_group_id
        except vmodl.MethodFault as method_fault:
            return True, dict(msg=method_fault.msg)
        except vmodl.RuntimeFault as runtime_fault:
            return True, dict(msg=runtime_fault.msg)

def core(module):

    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    vcluster = module.params.get('cluster')

    v = Getresgroupvms(vcsvr)
    conn = v.si_connection(vcsvr, vuser, vpass, vport)

    try:
        status, cluster = v.get_target_object(conn, [vim.ClusterComputeResource], vcluster)
        if not status:
            resourcepool_id = v.get_resourcepool_id(cluster)
            result = resourcepool_id
            failed = False
            return failed, result
        elif status:
            failmsg = "ERROR: %s" % cluster
            failed = True
            return failed, failmsg
    except Exception as e:
        return True, dict(msg=str(e))

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            cluster=dict(type='str', required=True),
            resourcevarname=dict(type='str', required=True)
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(changed=False, msg=result)
    else:
        ansible_facts_dict = {
            "changed": False,
            "ansible_facts": {

            }
        }
        resource_pool_id = result
        resource_pool_name = module.params.get('resourcevarname')
        ansible_facts_dict['ansible_facts'].update({resource_pool_name: resource_pool_id})
        ansible_facts_dict['changed'] = True
        print json.dumps(ansible_facts_dict)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()
