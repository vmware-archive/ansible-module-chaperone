#!/usr/bin/python

import atexit

try:
    import json
except ImportError:
    import simplejson as json

try:
  from pyVim import connect
  from pyVmomi import vmodl
except ImportError:
  module.fail_json(msg='pyVmomi is required')

def main():
    module = AnsibleModule(
        argument_spec=dict(
            vcenter_host=dict(required=True, default=None),
            vcenter_user=dict(required=True, default=None),
            vcenter_password=dict(required=True, default=None),
            vcenter_port=dict(required=True, type='int', default=None),
            vm_name=dict(required=True, default=None)
        )
    )

    vcenter_host = module.params.get('vcenter_host')
    vcenter_user = module.params.get('vcenter_user')
    vcenter_password = module.params.get('vcenter_password')
    vcenter_port = module.params.get('vcenter_port')
    vm_name = module.params.get('vm_name')

    try:
        # @todo - Need to add error handler for connection timeout?
        service_instance = connect.SmartConnect(host=vcenter_host,
                                                user=vcenter_user,
                                                pwd=vcenter_password,
                                                port=vcenter_port)

        atexit.register(connect.Disconnect, service_instance)
        content = service_instance.RetrieveContent()

        children = content.rootFolder.childEntity
        for child in children:
            if hasattr(child, 'vmFolder'):
                datacenter = child
            else:
                continue

            vm_folder = datacenter.vmFolder
            vm_list = vm_folder.childEntity

            for virtual_machine in vm_list:
                check_vm_and_children(vm_name, virtual_machine, 1, module)

        module.exit_json(msg="Appliance does not exist.")

    except vmodl.MethodFault as error:
        module.fail_json(msg="vmodl.MethodFault")

def check_vm_and_children(vm_name, virtual_machine, depth, module):
    max_depth = 10
    if depth > max_depth:
        return

    if virtual_machine.name == vm_name:
        module.exit_json(msg="Appliance exists!")

    if hasattr(virtual_machine, 'childEntity'):
        vmList = virtual_machine.childEntity
        child_depth = depth + 1
        for c in vmList:
            check_vm_and_children(vm_name, c, child_depth, module)

from ansible.module_utils.basic import *
if __name__ == "__main__":
    main()
