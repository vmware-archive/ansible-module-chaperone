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

import ssl
if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

DOCUMENTATION = '''
---
module: dc_cluster
Short_description: Create Datacenter and clusters in vCenter 
description:
    - Provides an interface to add datacenters and clusters to a vCenter instance. 
version_added: "0.1"
options:
    host:
        description:
            - Address to connect to the vCenter instance.
        required: True
        default: null
    login:
        description:
            - Username to login to vCenter instance.
        required: True
        default: null
    password:
        description:
            - Password to authenticate to vCenter instance.
        required: True
        default: null
    datacenter:
        description:
            - Datacenter structure that is expected to be created on the vCenter instance. 
        required: True
        default: null

author: Devin Nance
'''

class DatacenterBuilder:

    def __init__(self, module):
        self.module = module
        self.vsphere_host  = module.params.get('host')

    def BuildDatacenter(self, user, password, datacenter):
        if self.vsphere_host is None or user is None or password is None or not datacenter:
            return True, dict(msg = 'Host, login, password, and datacenter are required fields')

        try:
            self.si = SmartConnect(host = self.vsphere_host, user = user, pwd = password)
            print "Connected...."
        except Exception as e:
            credentials = self.vsphere_host + " " + user +  " " + password
            self.module.fail_json(msg = 'Could not connect to host %s: %s' % (credentials, str(e)))

        content = self.si.RetrieveContent()
        folder = content.rootFolder
        dc = folder.CreateDatacenter(name=datacenter['name'])
        clusters = datacenter['clusters']
        host_folder = dc.hostFolder
        cluster_spec = vim.cluster.ConfigSpecEx()
        for cluster in clusters:
            cluster = host_folder.CreateClusterEx(name=cluster['name'], spec=cluster_spec)

        atexit.register(Disconnect, self.si)
        print "Disconnected...."
        return False, dict(msg = 'Datacenter created successfully')

def core(module):
    user = module.params.get('login')
    password = module.params.get('password')
    datacenter = module.params.get('datacenter', dict())

    dcBuilder = DatacenterBuilder(module)
    fail, res = dcBuilder.BuildDatacenter(user, password,  datacenter)
    return fail, res


def main():
    module = AnsibleModule(
        argument_spec = dict(
            host = dict(required=True),
            login = dict(required=True),
            password = dict(required=True),
            datacenter = dict(type = 'dict', required=True)
        )
    )

    try:
        failed, result = core(module)
    except Exception as e:
        import traceback
        module.fail_json(msg = '%s: %s\n%s' %(e.__class__.__name__, str(e), traceback.format_exc()))

    if failed:
        module.fail_json(**result)
    else:
        module.exit_json(**result)

from ansible.module_utils.basic import *
main()
