#!/usr/bin/python
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

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
import paramiko
import socket
import time

DOCUMENTATION = '''
---
module: set_vcsa_sh
short_description: Set the default shell for a vCenter Server Appliance
description:
 - Set the default shell for a vCenter Server Appliance
version_added: "0.1"
options:
  hostname:
    description:
    - Address of vCenter Server Appliance
    required: True
    default: null
  port:
    description:
    - Port that SSH is running on
    required: True
    default: null
  username:
    description:
    - vCenter username
    required: True
    default: null
  password:
    description:
    - vCenter password
    required: True
    default: null
  shell:
    description:
    - Default shell for root user
    required: False
    default: /bin/bash
author: Charles Paul
'''

if __name__=="__main__":
  argument_spec = dict(
    hostname=dict(type='str',required=True),
    port=dict(type='int',required=True),
    username=dict(type='str',required=True),
    password=dict(type='str',required=True),
    shell=dict(type='str', required=False, default='/bin/bash')
  )
  module = AnsibleModule(argument_spec=argument_spec,supports_check_mode=True)
  HOSTNAME=module.params.get('hostname')
  PORT=module.params.get('port')
  USERNAME=module.params.get('username')
  PASSWORD=module.params.get('password')
  SHELL=module.params.get('shell')
  ssh = paramiko.SSHClient()
  ssh.load_system_host_keys()
  ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
  try:
    ssh.connect(HOSTNAME,PORT,USERNAME,PASSWORD)
  except Exception as e:
    import traceback
    module.fail_json(msg = '%s: %s %s %s\n%s' %(e.__class__.__name__, socket.getfqdn(HOSTNAME), PORT, str(e), traceback.format_exc()))
  chan = ssh.invoke_shell()
  chan.send("shell.set --enabled True --timeout 2147483647\n")
  time.sleep(1)
  chan.send("shell\n")
  time.sleep(1)
  sink = chan.send("chsh -s " + SHELL +" root \n")
  time.sleep(1)
