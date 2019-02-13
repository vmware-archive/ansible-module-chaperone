#!/usr/bin/env python
# coding=utf-8
#
# Copyright © 2015 VMware, Inc. All Rights Reserved.
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
