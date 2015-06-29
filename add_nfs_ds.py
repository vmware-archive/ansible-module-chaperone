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
module: add_nfs_ds
Short_description: Create NFS datastore and attache to all hosts in all cluster in datacenter
description:
    - Provides an interface to add nfs datastore to all hosts in clusters.
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
    nfshost:
        description:
            - hostname/ip of the nfs service.
        required: True
        default: null
    nfspath:
        description:
            - path to nfs share ex: /nfs
        required: True
        default: null
    nfsname:
        description:
            - name of nfs datastore in vcenter
        required: True
        default: null
    nfsaccess:
        description:
            - type of access if not readWrite specified on the nfs service, module will fail
        required: False
        default: readWrite
    nfstype:
        description:
            - type of datastore specified, NFS
        required: False
        default: NFS
'''

class Createdsnfs(object):
    def __init__(self, module):
        self.module = module

    def si_connection(self, vhost, user, password, port):
        try:
            self.SI = SmartConnect(host=vhost, user=user, pwd=password, port=port)
        except:
            creds = vhost + " " + user + " " + password
            self.module.fail_json(msg='Cannot connect %s' % creds)
        return self.SI

    def get_content(self, connection):
        try:
            content = connection.RetrieveContent()
            return content
        except vmodl.MethodFault as e:
            return module.fail_json(msg=e.msg)

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
            return True, dict(msg=meth_fault.msg)
        except vmodl.RuntimeFault as run_fault:
            return True, dict(msg=run_fault.msg)

    def get_datacenter(self, connection, vimtype, datacenter_name):
        status, datacenter_object_ref = self.get_vcobjt_byname(connection, vimtype, datacenter_name)
        if not status:
            return False, datacenter_object_ref
        else:
            return True, datacenter_object_ref

    def nas_spec(self, nfshost, nfspath, nfsname, nfsaccess, nfstype):
        nas_spec = vim.host.NasVolume.Specification(remoteHost=nfshost,
                                                    remotePath=nfspath,
                                                    localPath=nfsname,
                                                    accessMode=nfsaccess,
                                                    type=nfstype)
        return nas_spec

    def create_nfs(self, clusters, nasconfigspec):
        for cluster in clusters:
            hosts_in_cluster = cluster.host
            try:
                for host in hosts_in_cluster:
                    host.configManager.datastoreSystem.CreateNasDatastore(spec=nasconfigspec)
            except vim.HostConfigFault as host_fault:
                return True, dict(msg=host_fault.msg)
            except vmodl.MethodFault as method_fault:
                return True, dict(msg=method_fault.msg)
        return False, dict(msg="Attached all hosts to nfs datastore")

def core(module):
    vcsvr = module.params.get('host')
    vuser = module.params.get('login')
    vpass = module.params.get('password')
    vport = module.params.get('port')
    vio_dc = module.params.get('datacenter', dict())
    vnfshost = module.params.get('nfshost')
    vnfspath = module.params.get('nfspath')
    vnfsname = module.params.get('nfsname')
    vnfsaccess = module.params.get('nfsaccess')
    vnfstype = module.params.get('nfstype')

    target_dc_name = vio_dc['name']
    v = Createdsnfs(module)
    c = v.si_connection(vcsvr, vuser, vpass, vport)

    try:
        status, target_dc_object = v.get_datacenter(c, [vim.Datacenter], target_dc_name)
        if not status:
            host_folder = target_dc_object.hostFolder
            clusters_list = host_folder.childEntity
            vnas_spec = v.nas_spec(vnfshost, vnfspath, vnfsname, vnfsaccess, vnfstype)
            fail, result = v.create_nfs(clusters_list, vnas_spec)
            return fail, result
    except Exception as e:
        return True, str(e)

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            datacenter=dict(type='dict', required=True),
            nfshost=dict(type='str', required=True),
            nfspath=dict(type='str', required=True),
            nfsname=dict(type='str', required=True),
            nfsaccess=dict(type='str', required=False, default='readWrite'),
            nfstype=dict(type='str', required=False, default='NFS')
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
