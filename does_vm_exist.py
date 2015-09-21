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
		max_depth = 10
		depth = 1

		children = content.rootFolder.childEntity
		for child in children:
			if hasattr(child, 'vmFolder'):
				datacenter = child
			else:
				continue

			vm_folder = datacenter.vmFolder
			vm_list = vm_folder.childEntity

			for virtual_machine in vm_list:
				if hasattr(virtual_machine, 'childEntity'):
					if depth > max_depth:
						return
					vmList = virtual_machine.childEntity
					for c in vmList:

						if c.name == vm_name:
							module.fail_json(msg="Appliance exists!")

			module.exit_json(msg="Appliance does not exist.")

	except vmodl.MethodFault as error:
		module.fail_json(msg="vmodl.MethodFault")

from ansible.module_utils.basic import *
if __name__ == "__main__":
		main()
