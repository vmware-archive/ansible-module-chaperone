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
module: ref_host_profile
Short_description: Creates a host profile from an exsisting esxi host
description:
    - Creates a host profile from an exsisting esxi host
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
    port:
        description:
            - Port to access vCenter instance.
        required: False
        default: 443
    esxhostname:
        description:
            - Name of the esxi host to extract the host profile from
        required: True
        default: Null
    hostprofilename:
        description:
            - Name of the new host profile to create
        required: True
        default: Null
'''

class Hostprofile(object):
    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except:
            creds = vhost + " " + user + " " + password
            self.module.fail_json(msg='Cannot connect with %s' % creds)
        return self.SI

    def get_content(self, connection):
        try:
            content = connection.RetrieveContent()
            return content
        except vmodl.MethodFault as e:
            return module.fail_json(msg=e.msg)

    def get_ref_host(self, connection, vimtype, target_host):
        try:
            content = self.get_content(connection)
            name_objcts = {}
            container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
            for managed_objt_ref in container.view:
                name_objcts.update({managed_objt_ref.name: managed_objt_ref})
            if target_host in name_objcts:
                for k, v in name_objcts.items():
                    if k == target_host:
                       return False, v
            else:
                return True, dict(msg='Name not found %s' % target_host)
        except vmodl.MethodFault as meth_fault:
            return True, dict(msg=meth_fault.msg)
        except vmodl.RuntimeFault as run_fault:
            return True, dict(msg=run_fault.msg)

    def host_profile_spec(self, hostprofilename, reference_host):
        hostprospec = vim.profile.host.HostProfile.HostBasedConfigSpec(name=hostprofilename,
                                                               enabled=True,
                                                               host=reference_host,
                                                               useHostProfileEngine=True)
        if hostprospec:
            return False, hostprospec
        else:
            return True, dict(msg='Failed to create spec')

    def create_host_profile(self, connection, hostprofilespec):
        try:
            content = self.get_content(connection)
            hostprofilemanager = content.hostProfileManager
            createprofile = hostprofilemanager.CreateProfile(createSpec=hostprofilespec)
        except vmodl.MethodFault as meth_fault:
            return True, dict(msg=meth_fault.msg)
        except vmodl.RuntimeFault as run_fault:
            return True, dict(msg=run_fault.msg)
        return False, createprofile.name

def core(module):
    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    ref_host_name = module.params.get('esxhostname')
    new_hostprofile_name = module.params.get('hostprofilename')

    v = Hostprofile(module)
    c = v.si_connection(vcsvr, vuser, vpass, vport)

    try:
        get_host_status, reference_host = v.get_ref_host(c, [], ref_host_name)
        if not get_host_status:
            host_pro_status, hostconfigspec = v.host_profile_spec(new_hostprofile_name, reference_host)
            if not host_pro_status:
                create_status, ref_profile = v.create_host_profile(c, hostconfigspec)
                return create_status, ref_profile
        else:
            return True, dict(msg=reference_host)
    except Exception as e:
        return True, dict(msg=str(e))

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            esxhostname=dict(type='str', required=True),
            hostprofilename=dict(type='str', required=True)
        )
    )

    try:
        fail, result = core(module)
        if fail:
            module.fail_json(msg=result)
        else:
            module.exit_json(msg=result)
    except Exception as e:
        import traceback
        module.fail_json(msg='%s: %s\n%s' % (e.__class__.__name__, str(e), traceback.format_exc()))

from ansible.module_utils.basic import *
main()
