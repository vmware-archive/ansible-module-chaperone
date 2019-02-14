#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright © 2019 VMware, Inc. All Rights Reserved.

# SPDX-License-Identifier: Apache-2.0

import json
import yaml
import subprocess
## LOGGER
import logging
logger = logging.getLogger('chaperone_details')
hdlr = logging.FileHandler('/var/log/chaperone/ChaperoneNSXtLog.log')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(funcName)s: %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(10)


    
def main():
    module = AnsibleModule(argument_spec=dict(), supports_check_mode=True)
    cmd = ["""ip address | grep 'ens160'| grep 'inet' | awk '{print $2}'"""]
    output =subprocess.check_output(cmd,shell=True)
    output = output.rstrip("\n")
    rest = output.replace("/24","")
    cmd1 = ["whoami"]
    output1 = subprocess.check_output(cmd1,shell=True)
    module.exit_json(changed=True, hostname=rest, username = output1.rstrip("\n"), msg='Got cert details')

    
        
    
from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
