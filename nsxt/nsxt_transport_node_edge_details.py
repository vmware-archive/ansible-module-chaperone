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
logger = logging.getLogger('vswitch')
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
    sub_dict = {}
    main_dict = {}
    main_list= list()
    stream1 = open('/var/lib/chaperone/answerfile.yml', 'r')    
    dict1 = yaml.load(stream1, Loader=yamlordereddictloader.Loader)

    try:
        for data in dict1:
            if data.startswith('check_edge_node') == True:
                sub_dict[data] = dict1[data]
        for count in range(len(sub_dict)):
            hostname = str(count+1) + "_host_name"
            tnnode = "_tn_node"+ str(count+1)+ "_name"
            for content in dict1: 
                if content.startswith('nsx_edge') == True:
                    if hostname in content:
                        main_dict["host_name"]=dict1[content]
                        logger.info(main_dict)
                    if tnnode in content:
                        main_dict["node_name"]=dict1[content]
                        #logger.info('Node_name {}'.format(dict1[content]))
                        logger.info(main_dict)
                        main_list.append(main_dict)
                        main_dict={}
        #logger.info(main_list)
        #logger.info(main_dict)             
        final_dict['transport_edge_nodes']=main_list
	module.exit_json(changed=True, id=final_dict, msg= "Successfully got the information")

    except Exception as err:
        module.fail_json(changed=False, msg= "Failure: %s" %(err))

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
