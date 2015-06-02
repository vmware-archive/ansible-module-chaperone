#!/usr/bin/python

try:
	from pyVmomi import vim, vmodl
	from pyVim import connect
	HAS_PYVMOMI = True
except ImportError:
	HAS_PYVMOMI = False

import ssl
if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

import time

def wait_for_task(task):
	while True:
		if task.info.state == vim.TaskInfo.State.success:
			return True, task.info.result
		if task.info.state == vim.TaskInfo.State.error:
			try:
				raise TaskError(task.info.error)
			except AttributeError:
				raise TaskError("An unknown error has occurred")
		if task.info.state == vim.TaskInfo.State.running:
			time.sleep(5)
		if task.info.state == vim.TaskInfo.State.queued:
			time.sleep(5)

def check_vds_state(module):
	vds_name = module.params['vds_name']
	try:
		content = module.params['content']
		vds = find_dvs_by_name(content, vds_name)
		if vds is None:
			return 'absent'
		else:
			return 'present'
	except vmodl.RuntimeFault as runtime_fault:
		module.fail_json(msg=runtime_fault.msg)
	except vmodl.MethodFault as method_fault:
		module.fail_json(msg=method_fault.msg)

def state_exit_unchanged(module):
	module.exit_json(changed=False)

def state_destroy_vds(module):
	# TODO
	module.exit_json(changed=False)

def state_create_vds(module):
	content = module.params['content']
	vds_name = module.params['vds_name']
	numUplinks = module.params['numUplinks']
	numPorts = module.params['numPorts']
	prodVersion = module.params['productVersion']
	networkIOControl = module.params['networkIOControl']
	netResMgmtEnabled = False
	if networkIOControl == 'True':
		netResMgmtEnabled = True
	network_folder = content.rootFolder.childEntity[0].networkFolder
	try:
		if not module.check_mode:
			uplink_port_names = []
			vds_create_spec = vim.DistributedVirtualSwitch.CreateSpec()
			vds_config_spec = vim.DistributedVirtualSwitch.ConfigSpec()
			vds_config_spec.name = vds_name
			vds_config_spec.uplinkPortPolicy = vim.DistributedVirtualSwitch.NameArrayUplinkPortPolicy()

			for x in range(numUplinks):
				uplink_port_names.append("%s Uplink %d" % (vds_name, x+1))
			vds_config_spec.uplinkPortPolicy.uplinkPortName = uplink_port_names
			vds_config_spec.numStandalonePorts = int(numPorts)

			vds_create_spec.configSpec = vds_config_spec
			vds_create_spec.productInfo = vim.dvs.ProductSpec(version=prodVersion)

			vds_capability = vim.DistributedVirtualSwitch.Capability()
			vds_feature_cap = vim.DistributedVirtualSwitch.FeatureCapability()
			#vds_feature_cap.networkResourceManagementSupported = netResMgmtEnabled
			vds_feature_cap.networkResourceManagementSupported = True
			vds_capability.featuresSupported = vds_feature_cap

			task = network_folder.CreateDVS_Task(vds_create_spec)
			wait_for_task(task)
			module.exit_json(changed=True)
	except Exception, e:
		module.fail_json(msg=str(e))

def main():
	argument_spec = dict(
		hostname=dict(type='str', required=True),
		vs_port=dict(type='str'),
		username=dict(type='str', aliases=['user', 'admin'], required=True),
		password=dict(type='str', aliases=['pass', 'pwd'], required=True, no_log=True),
		vds_name=dict(type='str', required=True),
		numUplinks=dict(type='int', required=True),
		numPorts=dict(type='int', required=True),
		networkIOControl=dict(type='str', required=True, choices=['True', 'False']),
		productVersion=dict(type='str', required=True, choices=['6.0.0', '5.5.0', '5.1.0', '5.0.0']),
		state=dict(required=True, choices=['present', 'absent'], type='str')
	)
	module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

	if not HAS_PYVMOMI:
		module.fail_json(msg='pyvmomi is required for this module')

	vds_states = {
		'absent': {
			'present': state_destroy_vds,
			'absent': state_exit_unchanged,
		},
		'present': {
			'present': state_exit_unchanged,
			'absent': state_create_vds,
		}
	}

	desired_state = module.params['state']

	si = connect.SmartConnect(host=module.params['hostname'],
					user=module.params['username'],
					pwd=module.params['password'],
					port=int(module.params['vs_port']))
	if not si:
		module.fail_json(msg="Could not connect to the specified host using specified "
			"username and password")

	content = si.RetrieveContent()
	module.params['content'] = content

	current_state = check_vds_state(module)
	vds_states[desired_state][current_state](module)

	connect.Disconnect(si)


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
	main()
