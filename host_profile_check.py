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

class Gethostprofile(object):

    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except Exception as e:
            creds = vhost + " " + user + " " + password
            self.module.fail_json(msg = 'Could not connect to host %s: %s' % (creds, str(e)))
        return self.SI

    def get_content(self,connection):
        content = connection.RetrieveContent()
        return content

    def get_hostprofile(self, connection):
        content = self.get_content(connection)
        folder = content.hostProfileManager.profile
        return folder

    def get_profile_name(self, connection, profile_name):
        host_profiles = self.get_hostprofile(connection)
        for host_profile in host_profiles:
            if host_profile.name == profile_name:
                return False, dict(msg='Success')
        else:
            return True, dict(msg='Failed')

def core(module):

    vchost = module.params.get('host')
    vcuser = module.params.get('login')
    vcpass = module.params.get('password')
    vcport = module.params.get('port')
    profile_name = module.params.get('profilename')

    host_obj = Gethostprofile(module)
    connect = host_obj.si_connection(vchost, vcuser, vcpass, vcport)

    fail, result = host_obj.get_profile_name(connect, profile_name)

    return fail, result


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            profilename=dict(type='str')
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
