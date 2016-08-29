#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2015 VMware, Inc. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
# to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import paramiko

def create_vc_session(module):
    try:
        # SSH connect to PSC
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(module.params['res_vcenter_ip'], 22, 'root',
                                module.params['res_password'])
    except:
        module.fail_json(msg='SSH connection to the PSC failed.')
    return ssh

def repoint_lb_url(module):

    ssh = create_vc_session(module)
    repoint_urls = '/usr/lib/vmware-vmafd/bin/vmafd-cli set-dc-name --server-name localhost --dc-name {}'.format(module.params['lb_fqdn'])
    stdout = ssh.exec_command(repoint_urls)

def stop_vcenter_services(module):
    ssh = create_vc_session(module)
    stdout = ssh.exec_command('service-control --stop --all')
    stat = check_command_status(stdout)

def start_vcenter_services(module):
    ssh = create_vc_session(module)
    stdout = ssh.exec_command('service-control --start --all')
    check_command_status(stdout)
    stat = check_command_status(stdout)

def check_command_status(stdout):
    max=700
    count = 0
    while True:
        stdout_line = str(stdout[0].readline)
        if stdout_line.find('active; 1') != -1:
            count = count + 15
            time.sleep(15)
            if count == max:
                module.fail_json(msg='Failed to Restart services')
        elif stdout_line.find('active; 0') != -1:
            break
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(default='present', choices=['present', 'absent']),
            res_vcenter_ip=dict(required=True),
            res_password=dict(required=True),
            lb_fqdn=dict(required=True),
            ),
        supports_check_mode=False
    )

    stat = repoint_lb_url(module)
    stop_vcenter_services(module)
    start_vcenter_services(module)
    module.exit_json(changed=True, argument_spec=module.params['state'])

from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()