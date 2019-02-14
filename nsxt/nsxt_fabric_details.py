#!/usr/bin/env python
#
# Copyright © 2015 VMware, Inc. All Rights Reserved.
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

import yaml
import yamlordereddictloader
from collections import OrderedDict

import paramiko
import time
from pyVmomi import vim, vmodl
from pyVim import connect
from pyVim.connect import SmartConnect, SmartConnectNoSSL

import logging
logger = logging.getLogger('nsxt_fabric_details')
hdlr = logging.FileHandler('/var/log/chaperone/ChaperoneNSXtLog.log')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(funcName)s: %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(10)

def getting_thumbprint(module,pi):      
    try:         
        command = "openssl x509 -in /etc/vmware/ssl/rui.crt -fingerprint -sha256 -noout"
        (sshin1, sshout1, ssherr1) = pi.exec_command(command)
        out = sshout1.read()
        output = out.split("=")[1]
        logger.info(output)
        return output.rstrip("\n")    
    except Exception as error:
       	logger.info("Error Occured:%s" %(error))
        module.fail_json(msg="Error Occured: %s" %error)
	
def main():
    module = AnsibleModule(
        argument_spec=dict(
        ),
        supports_check_mode=True
    )
    username = "root"
    final_dict = {}
    main_list = list()
    main_dict = {}
    stream = open('/var/lib/chaperone/answerfile.yml', 'r')    
    dict1 = yaml.load(stream, Loader=yamlordereddictloader.Loader)
    try:
        for key in dict1:
            if key.startswith('esxi_compute') == True:
            	if "ip" in key:
                    main_dict["display_name"]=dict1[key]
                    main_dict["ip_address"]=dict1[key]
                    logger.info(main_dict)
                if "os_version" in key:
                    main_dict["os_version"]=dict1[key]
                if "password" in key:
                    main_dict["host_password"]=dict1[key]
                    logger.info(main_dict)

                    main_list.append(main_dict)
                    logger.info(main_dict)
                    logger.info(main_list)                  
                    main_dict={}      
        logger.info(main_list)           
        pi = paramiko.client.SSHClient()
        pi.load_system_host_keys()
        pi.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
        for i in range(0,len(main_list)):
            logger.info(main_list[i]["ip_address"])           
            pi.connect(main_list[i]["ip_address"], 22, username, main_list[i]["host_password"])
	    logger.info('Esxi host connection succeed...........')
	    thumb_prints= getting_thumbprint(module,pi)
	    main_list[i]["host_thumbprint"]=thumb_prints
        logger.info(main_list)
        final_dict['fabric_host_nodes']=main_list
        module.exit_json(changed=True, result=final_dict, msg= "Successfully got the Fabric Host Nodes information")

    except Exception as err:
        module.fail_json(changed=False, msg= "Failure: %s" %(err))

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
