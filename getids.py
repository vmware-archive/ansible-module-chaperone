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

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
except ImportError:
    print("failed=True msg='pyVmomi is required to run this module'")


class vcenterids(object):

    cluster_res = 'host'
    network_res = 'network'
    data_res = 'data'

    def __init__(self, module):
        self.module = module
        self.vhost = module.params.get('host')
        login_user = module.params.get('login')
        login_password = module.params.get('password')
        self.port = module.params.get('port')
        self.folder_type = module.params.get('resourcetype')

        try:
            self.si = SmartConnect(host=self.vhost, user=login_user, pwd=login_password, port =self.port)
        except:
            creds = "host: %s user: %s pass: %s port: %s" % (self.vhost, login_user, login_password, self.port)
            self.module.fail_json(msg='Could not connect to vctr %s' % creds)

    @property
    def content(self):
        if not hasattr(self, '_content'):
            self._content = self.si.RetrieveContent()
        return self._content

    def get_rootfolder(self):
        dc_r = self.content.rootFolder.childEntity
        return dc_r

    def get_resource_folder(self, top_root, folder_type):
        if folder_type == 'cluster':
            rec_folder = top_root.hostFolder.childEntity
            return rec_folder
        if folder_type == 'network':
            rec_folder = top_root.networkFolder.childEntity
            return rec_folder
        if folder_type == 'data':
            rec_folder = top_root.datastoreFolder.childEntity
            return rec_folder

    def get_names(self, top_path, name_list):
        path_list = top_path
        p = len(path_list)
        for i in range(0, p):
            dc_obj = path_list[i]
            name = dc_obj.name
            name_string = str(name)
            name_list.append(name_string)

    def get_ids_obj(self, top_path, target_name):
        path_list = top_path
        p = len(path_list)
        for i in range(0, p):
            dc_obj = path_list[i]
            name = dc_obj.name
            name_string = str(name)
            if name_string == target_name:
                return dc_obj
            else:
                var_is = 0

    def get_ids_str(self, top_path, target_name):
        path_list = top_path
        p = len(path_list)
        for i in range(0, p):
            dc_obj = path_list[i]
            name = dc_obj.name
            name_string = str(name)
            if name_string == target_name:
                to_string = str(dc_obj)
                dc_obj_str = to_string.split(':')
                target_id = dc_obj_str[1]
                new_target_id = target_id.replace("'", "")
                obj_id = new_target_id
                return obj_id
            else:
                var_is = 0

    def name_id_json(self, target_dc, t_folder):
        the_hash = {}
        the_names = []
        rootfolder = self.get_rootfolder()
        dc = self.get_ids_obj(rootfolder, target_dc)
        #res_folder = self.get_resource_folder(dc, target_rec)
        res_folder = self.get_resource_folder(dc, t_folder)
        self.get_names(res_folder, the_names)
        for i in the_names:
            the_hash[i] = self.get_ids_str(res_folder, i)
        the_json = json.dumps(the_hash, ensure_ascii=False)
        return the_json
        #return fail, the_json



def core(module):
    datacenter = module.params.get('datacenter')
    res_type = module.params.get('resourcetype')

    v = vcenterids(module)
    ids = v.name_id_json(datacenter, res_type)

    if ids:
        fail = False
        res = ids
    else:
        fail = True
        res = dict(msg='Failed')

    return fail, res


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type = 'str'),
            datacenter=dict(type='str'),
            resourcetype=dict(type='str'),
            timeout=dict(type='int', default=60),
            get_facts=dict(default="yes", required=False)
        )
    )

    ansible_facts_dict = {
        "changed" : False,
        "ansible_facts": {
            }
    }

    fail, result = core(module)

    if module.params['resourcetype'] == 'network':
        ansible_netids = result
        ansible_facts_dict['ansible_facts']['ansible_netids'] = ansible_netids

    if module.params['resourcetype'] == 'cluster':
        ansible_clusterids = result
        ansible_facts_dict['ansible_facts']['ansible_clusterids'] = ansible_clusterids

    if module.params['resourcetype'] == 'data':
        ansible_dataids = result
        ansible_facts_dict['ansible_facts']['ansible_dataids'] = ansible_dataids


    if fail:
        module.fail_json(**result)
    else:
        print json.dumps(ansible_facts_dict)
        #return json.dumps(ansible_facts_dict)
        #module.exit_json(**result)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()
