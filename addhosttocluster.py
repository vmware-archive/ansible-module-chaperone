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
module: addhosttocluster
Short_description: add a specified host to a vcenter cluster
description:
    - add a specified host to a vcenter cluster.
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
    clustername:
        description:
            - Name of the cluster you are adding the host to.
        required: True
        default: null
    esxhostname:
        description:
            - Hostname/IP of the esxi host adding to the cluster.
        required: True
        default: null
    esxusername:
        description:
            - username for accessing the esxi host usually 'root'.
        required: True
        default: null
    esxpassword:
        description:
            - password to access the esxi host via shell
        required: True
        default: null
    esxsslthumbprint:
        description:
            - SSL Thumbprint for the esxi host
        required: True
        default: null
'''
EXAMPLES = '''
- name: Get ssl thumbprint for esxi host
  local_action: command echo -n | openssl s_client -connect "{{ esxi_hostname_or_ip }}":443 2>/dev/null | openssl x509 -noout -fingerprint -sha1
  register: esx_ssl_thumbprint

- name: Add Host to Cluster
  ignore_errors: yes
  local_action:
    module: addhosttocluster
    host: vcenter_host_or_ip
    login: administrator@vsphere.local
    password: VMware1!
    port: 443
    clustername: 'supervio-cluster'
    esxhostname: 'esx-supervio-host'
    esxusername: 'root'
    esxpassword: 'VMware1!'
    esxsslthumbprint: "{{ esx_ssl_thumbprint.stdout }}"

'''

class Addhostcluster(object):
    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except:
            creds = vhost + " " + user + " " + password
            print 'Cannot connect %s' % creds
        return self.SI

    def get_content(self, connection):
        try:
            content = connection.RetrieveContent()
            return content
        except vmodl.MethodFault as e:
            return e.msg

    def get_vcobjt_byname(self, connection, vimtype, target_name):
        content = self.get_content(connection)
        vc_objt = {}
        try:
            container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
            for managed_object_ref in container.view:
                vc_objt.update({managed_object_ref.name: managed_object_ref})
            for k, v in vc_objt.items():
                if k == target_name:
                    return False, v
        except vmodl.MethodFault as meth_fault:
            return True, meth_fault.msg
        except vmodl.RuntimeFault as run_fault:
            return True, run_fault.msg

    def hostspec(self, host_name, sslprint, user_name, pass_word):
        hostconnectspec = vim.host.ConnectSpec(hostName=host_name,
                                               sslThumbprint=sslprint,
                                               userName=user_name,
                                               password=pass_word)
        return hostconnectspec

    def task_check(self, task):
        while True:
            if task.info.state == vim.TaskInfo.State.error:
                return True, task.info.error.msg
            if task.info.state == vim.TaskInfo.State.success:
                return False, task.info.result
            else:
                time.sleep(5)

    def addhosttocluster(self, cluster_object, hostspecifictation):
        try:
            add_host_task = cluster_object.AddHost(spec=hostspecifictation,
                                                   asConnected=True)
            status, task_status = self.task_check(add_host_task)
        except vmodl.MethodFault as method_fault:
            return True, dict(msg=method_fault.msg)
        except vmodl.RuntimeFault as runtime_fault:
            return True, dict(msg=runtime_fault.msg)
        return status, task_status

def core(module):
    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    vcluster_name = module.params.get('clustername')
    vesxhostname = module.params.get('esxhostname')
    vesxusername = module.params.get('esxusername')
    vesxpassword = module.params.get('esxpassword')
    vesxssl = module.params.get('esxsslthumbprint')

    v = Addhostcluster(module)
    connection = v.si_connection(vcsvr, vuser, vpass, vport)
    clust_status, cluster_objt_ref = v.get_vcobjt_byname(connection, [vim.ClusterComputeResource], vcluster_name)
    hostconfig_spec = v.hostspec(vesxhostname, vesxssl, vesxusername, vesxpassword)

    task_status, addhosttask = v.addhosttocluster(cluster_objt_ref, hostconfig_spec)

    if not task_status:
        return task_status, dict(msg=addhosttask.name)
    elif task_status:
        return task_status, dict(msg=addhosttask)

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            clustername=dict(type='str', required=True),
            esxhostname=dict(type='str', required=True),
            esxusername=dict(type='str', required=True),
            esxpassword=dict(type='str', required=True)
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(**result)
    else:
        module.exit_json(msg=result)

from ansible.module_utils.basic import *
main()
