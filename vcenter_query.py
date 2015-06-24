#!/usr/bin/env python

try:
    import json
except ImportError:
    import simplejson as json

import re
import os
import time
import atexit
import urllib2
import datetime
import ast

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
            - vCenter inventory object name
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
            - cluster, datacenter, datastore, dvs, dvs-port
        required: True
        default: Null
    getfacts:
        description:
            - valid options
        required: False
        default: yes
'''
EXAMPLES = '''
- name: Get vCenter ID
  ignore_errors: yes
  local_action:
    module: vcenter_query
    host: vcenter_host
    login: vcenter_user
    password: vcenter_password
    port: vcenter_port
    resourcename: "{{ item.vcenter_object_name }}"
    resourcevarname: "{{ item.vcenter_object_var }}"
    resourcetype: 'cluster'
    getfacts: 'yes'
  with_items:
    - { vcenter_object_name: "{{ vio_cluster_mgmt }}", vcenter_object_var: 'vio_cluster_mgmt_id' }
    - { vcenter_object_name: "{{ vio_cluster_edge }}", vcenter_object_var: 'vio_cluster_edge_id' }
    - { vcenter_object_name: "{{ vio_cluster_compute }}", vcenter_object_var: 'vio_cluster_compute_id' }
'''

class Getnamesids(object):
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
        content = connection.RetrieveContent()
        return content

    def get_ids_dc(self, connection, vimtype):
        content = self.get_content(connection)
        name_id = {}
        container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
        for managed_object_ref in container.view:
            mor_id = str(managed_object_ref).split(':')[1].replace("'", "")
            name_id.update({managed_object_ref.name: mor_id})
        return name_id

    def get_id_name(self, connection, vimtype, target_name):
        vc_objts = self.get_ids_dc(connection, vimtype)
        if target_name in vc_objts:
            for k, v in vc_objts.iteritems():
                if k == target_name:
                    return v
            else:
                return None


def core(module):

    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    rec_name = module.params.get('resourcename')
    rec_type = module.params.get('resourcetype')

    vim_rec_type = {
        'cluster': vim.ClusterComputeResource,
        'datacenter': vim.Datacenter,
        'datastore': vim.Datastore,
        'dvs': vim.DistributedVirtualSwitch,
        'dvs-port': vim.Network
    }

    names_ids = Getnamesids(module)
    connect = names_ids.si_connection(vcsvr, vuser, vpass, vport)
    vim_type = vim_rec_type[rec_type]
    target_id = names_ids.get_id_name(connect, [vim_type], rec_name)

    if target_id is not None:
        return False, target_id
    else:
        return True, dict(msg='Failed to Find Resource Name')

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
            getfacts=dict(default="yes", required=False)
        )
    )

    fail, result = core(module)

    ansible_facts_dict = {
        "changed": False,
        "ansible_facts": {

        }
    }

    resource_id = result
    resource_var = module.params.get('resourcevarname')
    ansible_facts_dict['ansible_facts'].update({resource_var: resource_id})
    ansible_facts_dict['changed'] = True

    if fail:
        module.fail_json(**result)
    else:
        print json.dumps(ansible_facts_dict)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()

