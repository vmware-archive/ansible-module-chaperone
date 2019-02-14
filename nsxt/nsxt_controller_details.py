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

import logging
logger = logging.getLogger('nsxt_controller_details')
hdlr = logging.FileHandler('/var/log/chaperone/ChaperoneNSXtLog.log')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(funcName)s: %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(10)

def main():
    module = AnsibleModule(
        argument_spec=dict(
        ),
        supports_check_mode=True
    )
    final_dict = {}
    main_list = list()
    main_dict = {}
    stream = open('/var/lib/chaperone/answerfile.yml', 'r')    
    dict1 = yaml.load(stream, Loader=yamlordereddictloader.Loader)
    try:
        for key in dict1:
            if key.startswith('nsx_controller') == True:
                if "host_name" in key:
                    main_dict["display_name"]=dict1[key]
            	if "ip" in key: 
                    main_dict["ip_address"]=dict1[key] 

                    logger.info(main_dict)
                    main_list.append(main_dict)
                    main_dict= {}    
        logger.info(main_list)
        logger.info(main_dict)            

        final_dict['Controller_nodes']=main_list
	module.exit_json(changed=True, result=final_dict, msg= "Successfully got the Controller Node information")
    except Exception as err:
        module.fail_json(changed=False, msg= "Failure: %s" %(err))

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
