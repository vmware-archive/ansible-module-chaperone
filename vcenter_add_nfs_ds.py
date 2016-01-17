#!/usr/bin/env python

DOCUMENTATION = '''
module: vcenter_add_nfs_ds
short_description: Add host to nfs datastore
description:
    - Add host to specified nfs datastore
options:
    host:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    login:
        description:
            - The username of the vSphere vCenter
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter
        required: True
        aliases: ['pass', 'pwd']
    port:
        description:
            - The TCP port of the vSphere API
        required: True
    esxi_hostname:
        description:
            - The esxi hostname or ip to add to nfs ds
        required: True
    nfs_host:
        description:
            - The nfs service providing nfs service
        required: True
    nfs_path:
        description:
            - The remove file path ex: /nfs1
        required: True
    nfs_name:
        description:
            - The name of the datastore as seen by vcenter
        required: True
    nfs_access:
        description:
            - The access type
        choices: [readWrite, readOnly]
        required: True
    nfs_type:
        description:
            - The type of volume. Defaults to nfs if not specified
        choices: [nfs, cifs]
        required: False
    nfs_username:
        description:
            - The username to access the nfs ds if required
        required: False
    nfs_password:
        description:
            - The password to access the nfs ds if required
        required: False
    state:
        description:
            - If the datacenter should be present or absent
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
- name: Add NFS DS to Host
  ignore_errors: no
  vcenter_add_nfs_ds:
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    esxi_hostname: '192.168.1.102'
    nfs_host: '192.168.1.145'
    nfs_path: '/nfs1'
    nfs_name: 'nfs_ds_1'
    nfs_access: 'readWrite'
    nfs_type: 'nfs'
    state: 'present'
  tags:
    - addnfs
'''

try:
    import atexit
    import time
    import requests
    import sys
    import collections
    from pyVim import connect
    from pyVmomi import vim, vmodl

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


def connect_to_vcenter(module, disconnect_atexit=True):
    hostname = module.params['host']
    username = module.params['login']
    password = module.params['password']
    port = module.params['port']

    try:
        service_instance = connect.SmartConnect(
            host=hostname,
            user=username,
            pwd=password,
            port=port
        )

        if disconnect_atexit:
            atexit.register(connect.Disconnect, service_instance)

        return service_instance.RetrieveContent()
    except vim.fault.InvalidLogin, invalid_login:
        module.fail_json(msg=invalid_login.msg, apierror=str(invalid_login))
    except requests.ConnectionError, connection_error:
        module.fail_json(msg="Unable to connect to vCenter or ESXi API on TCP/443.", apierror=str(connection_error))


def get_all_objects(content, vimtype):
    obj = {}
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for managed_object_ref in container.view:
        obj.update({managed_object_ref: managed_object_ref.name})
    return obj


def find_vcenter_object_by_name(content, vimtype, object_name):
    vcenter_object = get_all_objects(content, [vimtype])

    for k, v in vcenter_object.items():
        if v == object_name:
            return k
    else:
        return None


def nfs_spec(module):

    nfs_remote_host = module.params['nfs_host']
    nfs_remote_path = module.params['nfs_path']
    nfs_local_name = module.params['nfs_name']
    nfs_access_mode = module.params['nfs_access']
    nfs_type = module.params['nfs_type']
    nfs_username = module.params['nfs_username']
    nfs_password = module.params['nfs_password']

    nfs_config_spec = vim.host.NasVolume.Specification(
        remoteHost=nfs_remote_host,
        remotePath=nfs_remote_path,
        localPath=nfs_local_name,
        accessMode=nfs_access_mode,
        type=nfs_type,
        userName=nfs_username,
        password=nfs_password,
    )

    return nfs_config_spec


def check_host_added_to_nfs_ds(module):

    nfs_ds = module.params['nfs']
    host = module.params['host']

    for esxhost in nfs_ds.host:
        if esxhost.key == host:
            return True
    else:
        return None


def state_exit_unchanged(module):
    module.exit_json(change=False)

def state_delete_nfs(module):

    host = module.params['host']
    ds = module.params['nfs']

    try:
        host.configManager.datastoreSystem.RemoveDatastore(ds)
    except Exception as e:
        module.fail_json(msg="Failed to remove datastore: %s" % str(e))

    result_msg = "Unmounted: %s from host: %s" % (ds.name, host.name)
    module.exit_json(changed=True, result=result_msg)

def state_create_nfs(module):

    host = module.params['host']
    ds_spec = nfs_spec(module)

    try:
        ds = host.configManager.datastoreSystem.CreateNasDatastore(ds_spec)
    except vim.fault.DuplicateName as duplicate_name:
        module.fail_json(msg="Failed duplicate name: %s" % duplicate_name)
    except vim.fault.AlreadyExists as already_exists:
        module.fail_json(msg="Failed already exists on host: %s" % already_exists)
    except vim.HostConfigFault as config_fault:
        module.fail_json(msg="Failed to configure nfs on host: %s" % config_fault.msg)
    except vmodl.fault.InvalidArgument as invalid_arg:
        module.fail_json(msg="Failed with invalid arg: %s" % invalid_arg)
    except vim.fault.NoVirtualNic as no_virt_nic:
        module.fail_json(msg="Failed no virtual nic: %s" % no_virt_nic)
    except vim.fault.NoGateway as no_gwy:
        module.fail_json(msg="Failed no gateway: %s" % no_gwy)
    except vmodl.MethoFault as method_fault:
        module.fail_json(msg="Failed to configure nfs on host method fault: %s" % method_fault.msg)

    result_msg = "Mounted host: %s on nfs: %s" % (host.name, ds.name)
    module.exit_json(change=True, result=result_msg)

def check_nfs_host_state(module):
    esxi_hostname = module.params['esxi_hostname']
    nfs_ds_name = module.params['nfs_name']

    content = connect_to_vcenter(module)
    module.params['content'] = content

    host = find_vcenter_object_by_name(content, vim.HostSystem, esxi_hostname)

    if host is None:
        module.fail_json(msg="Esxi host: %s not in vcenter" % esxi_hostname)
    module.params['host'] = host

    nfs_ds = find_vcenter_object_by_name(content, vim.Datastore, nfs_ds_name)

    if nfs_ds is None:
        return 'absent'
    else:
        module.params['nfs'] = nfs_ds

        if check_host_added_to_nfs_ds(module):
            return 'present'
        else:
            return 'update'



def main():
    argument_spec = dict(
        host=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        port=dict(required=True, type='int'),
        esxi_hostname=dict(required=True, type='str'),
        nfs_host=dict(required=True, type='str'),
        nfs_path=dict(required=True, type='str'),
        nfs_name=dict(required=True, type='str'),
        nfs_access=dict(required=True, type='str'),
        nfs_type=dict(required=False, type='str'),
        nfs_username=dict(required=False, type='str'),
        nfs_password=dict(required=False, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        nfs_host_states = {
            'absent': {
                'update': state_exit_unchanged,
                'present': state_delete_nfs,
                'absent': state_exit_unchanged,
            },
            'present': {
                'update': state_create_nfs,
                'present': state_exit_unchanged,
                'absent': state_create_nfs,
            }
        }

        nfs_host_states[module.params['state']][check_nfs_host_state(module)](module)

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
