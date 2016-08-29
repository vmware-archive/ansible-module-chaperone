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

import os
import paramiko
import time

def create_psc_session(module, psc_ip, password):
    try:
        #Transport connection to the PSC
        transport = paramiko.Transport(psc_ip, 22)
        transport.connect(username='root', password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
    except:
        module.fail_json(msg='Transport connection to the PSC failed.')
    try:
        # SSH connect to PSC
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(psc_ip, 22, 'root', password)
    except:
        module.fail_json(msg='SSH connection to the PSC failed.')
    return sftp, ssh

def copy_ha_scripts_first_psc(module):
    sftp, ssh = create_psc_session(module, module.params['psc_1_ip'],
                                   module.params['psc_password'])
    #psc_dirs = sftp.listdir('/')
    sftp.mkdir('/ha')
    sftp.mkdir('/ha/keys')

    script_path='/opt/chaperone-ansible/roles/vcloud-nfv-ra/files/psc-ha-script'
    ha_files = os.listdir(script_path)
    for f in ha_files:
        sftp.put(os.path.join(script_path, f), '/ha/'+f)

def generate_lb_certificate_first_psc(module):
    sftp, ssh = create_psc_session(module, module.params['psc_1_ip'],
                                   module.params['psc_password'])
    cert_gen_cmd = 'cd /ha \n python gen-lb-cert.py --primary-node --lb-fqdn={}'.format(module.params['lb_fqdn'])
    stdout = ssh.exec_command(cert_gen_cmd)
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

def copy_keys_directory(module):
    sftp, ssh = create_psc_session(module, module.params['psc_1_ip'], 
                                   module.params['psc_password'])
    # copy keys to HA folder
    ssh.exec_command('cp -r /etc/vmware-sso/keys/* /ha/keys')

def copy_ha_directory(module):
    '''Copy Ha directory to Second PSC
    '''
    sftp, ssh = create_psc_session(module, module.params['psc_1_ip'], 
                                   module.params['psc_password'])
    # Copy whole Ha folder to Second PSC
    scp_cmd = 'sshpass -p "VMware1!" scp  -o StrictHostKeyChecking=no -r /ha root@{}:/'.format(module.params['psc_2_ip'])
    ssh.exec_command(scp_cmd)

def generate_cert_on_second_psc(module):
    sftp, ssh = create_psc_session(module, module.params['psc_2_ip'], 
                                   module.params['psc_password'])
    gen_cert_cmd='echo "" | python /ha/gen-lb-cert.py --secondary-node --lb-fqdn={} --lb-cert-folder=/ha --sso-serversign-folder=/ha/keys'.format(module.params['lb_fqdn'])
    stdout = ssh.exec_command(gen_cert_cmd)
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

def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(default='present', choices=['present', 'absent']),
            psc_1_ip=dict(required=True),
            psc_2_ip=dict(required=True),
            psc_password=dict(required=True),
            virtual_ip=dict(required=True),
            lb_fqdn=dict(required=True),
            ),
        supports_check_mode=False
    )
    copy_ha_scripts_first_psc(module)
    generate_lb_certificate_first_psc(module)
    copy_keys_directory(module)
    copy_ha_directory(module)
    generate_cert_on_second_psc(module)
    module.exit_json(changed=True, argument_spec=module.params['state'])

from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
