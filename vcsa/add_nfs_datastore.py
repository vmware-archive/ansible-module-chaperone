#!/usr/bin/env python
#
# (c) 2015, Joseph Callen <jcallen () csc.com>
# Portions Copyright (c) 2015 VMware, Inc. All rights reserved.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


DOCUMENTATION = '''
module: add_nfs_datastore
short_description: Add NFS Datastore
description:
    - Adds an NFS Datastore to an ESXi
options:
    state:
        description:
            - Add NFS Datastore
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Adds an NFS Datastore to an ESXi
  ignore_errors: no
  add_nfs_datastore:
	hostip: "{{ host_ip }}"
	hostusername: "{{ host_username }}"
	hostpassword: "{{ host_password }}"
	nfsip : "{{ nfs_ip  }}"
	mountpoint: "{{ mount_point }}"
	datastorename: "{{ datastore_ename }}"
    state: 'present'
  tags:
    - add_datastore
'''

import time
import requests
import paramiko
import os
import select

def state_exit_unchanged(module):
    module.exit_json(changed=False)

def check_esxids_state(module):
	#Need logic to check state
    return 'absent'

def state_destroy_esxids(module):
	#Need logic to remove nfs datastore
    return 'absent'
def state_create_esxids(module):

	changed=True
	LOG_FILE = "filename.log"

	hostip= module.params['hostip']
	hostusername = module.params['hostusername']
	hostpassword = module.params['hostpassword']
	nfsip = module.params['nfsip']
	mountpoint = module.params['mountpoint']
	datastorename = module.params['datastorename']

	#SSH CONNECTION TO VCD CELL
	try:
		ssh = paramiko.SSHClient()
		paramiko.util.log_to_file(LOG_FILE)
		ssh.load_system_host_keys()
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		ssh.connect(hostip, 22, hostusername, hostpassword)
	except:
		changed = False
		module.fail_json(msg='SSH conection to the remote host failed.')


	cmd = 'esxcli storage nfs add -H=' + nfsip + ' -s ' + mountpoint + ' -v ' + datastorename

	try:
		stdin, stdout, stderr = ssh.exec_command(cmd)
	except:
		changed = False
		module.fail_json(msg='Failed to add NFS Datastore')

	if changed:
		module.exit_json(changed=changed, result="NFS" + datastorename + " successfully Mounted to ESXi")



def main():
    argument_spec = dict(

		hostip=dict(required=True, type='str'),
		hostusername=dict(required=True, type='str'),
		hostpassword=dict(required=True, type='str'),
		nfsip=dict(required=True, type='str'),
		mountpoint=dict(required=True, type='str'),
		datastorename=dict(required=True, type='str'),
		state=dict(required=True, choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)


    esxi_states = {
        'absent': {
            'present': state_destroy_esxids,
            'absent': state_exit_unchanged,
        },
        'present': {
            'present': state_exit_unchanged,
            'absent': state_create_esxids,
        }
    }
    desired_state = module.params['state']
    current_state = check_esxids_state(module)

    esxi_states[desired_state][current_state](module)


from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
