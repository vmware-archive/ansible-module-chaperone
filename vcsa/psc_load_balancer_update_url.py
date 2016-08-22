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

def create_psc_session(module):
    try:
        # SSH connect to PSC
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(module.params['psc_1_ip'], 22, 'root',
                    module.params['psc_password'])
    except:
        module.fail_json(msg='SSH connection to the PSC failed.')
    return ssh

def update_lb_end_points(module):
    ssh = create_psc_session(module)
    end_point_cmd = 'cd /ha \n python lstoolHA.py --hostname={} --lb-fqdn={} --lb-cert-folder=/ha --user={} --password={}'.format(module.params['psc_1_fqdn'],
                                                module.params['lb_fqdn'],
                                                module.params['psc_username'],
                                                module.params['psc_password'],
                                                )
    stdout = ssh.exec_command(end_point_cmd)
    max=400
    count = 0
    while True:
        stdout_line = str(stdout[0].readline)
        if stdout_line.find('active; 1') != -1:
            count = count + 15
            time.sleep(15)
            if count == max:
                module.fail_json(msg='PSC HA pairing failed, please check manually')
        elif stdout_line.find('active; 0') != -1:
            break

    module.exit_json(changed=True, argument_spec=module.params['state'])

def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(default='present', choices=['present', 'absent']),
            psc_1_ip=dict(required=True),
            psc_1_fqdn=dict(required=True),
            lb_fqdn=dict(required=True),
            psc_username=dict(required=True),
            psc_password=dict(required=True),
            ),
        supports_check_mode=False
    )
    update_lb_end_points(module)


from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
