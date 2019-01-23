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
    username = "root"
    final_dict = {}
    sub_dict = {}
    main_dict = {}
    main_list= list()
    content_dict={}
    final_list = list()
    imp_list=list()
    stream1 = open('/var/lib/chaperone/answerfile.yml', 'r')    
    dict1 = yaml.load(stream1, Loader=yamlordereddictloader.Loader)

    try:
        for data in dict1:
            if data.startswith('check_edge_node') == True:
                sub_dict[data] = dict1[data]
        for content in dict1: 
            if content.startswith('esxi_compute') == True:
                if 'host' in content and 'ip' in content:
                    main_dict["ip_address"]=dict1[content]
                    logger.info(main_dict)
                if 'host' in content and 'vmnic' in content:
                    main_dict["vmnic"]=dict1[content]
                    logger.info(main_dict)
                    main_list.append(main_dict)
                    main_dict={}
        #logger.info(main_list)
        #logger.info(main_dict)             
        final_dict['transport_host_nodes']=main_list
	module.exit_json(changed=True, id=final_dict, msg= "Successfully got the information")

    except Exception as err:
        module.fail_json(changed=False, msg= "Failure: %s" %(err))

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
