#!/usr/bin/python
__author__ = 'smetta'
# Import the module
import subprocess
DOCUMENTATION = '''
---
module: vraova_deploy
Short_description: Module for deploying VRA ova
description:
    - Provides an interface for deployment of ova in venter
versoin_added: "0.1"
options:
    vcenter_props:
        description:
            - Dictionary containing vcenter properties.
        required: True
        default: Null
    location_props:
        description:
            - Dictionary containing the location properties of appliance
        required: True
        default: Null
    ova_props:
        description:
            - Dictionary containing the directory and name of the ova file
        required: True
        default: Null
   resource_props
        description:
            - Dictionary containing the properties of the appliance itself
        required: True
        default: Null
    additional_props::
        description:
            - Dictionary containing additional properties of ova such as diskmode, IP  protocol
        required: True
    option_props:
        description:
            - List of options that can be specified for  ovf tool
        required: True
        default: null
'''
EXAMPLES = '''
- name: Deploy  ova through Python
  ignore_errors: yes
  local_action:
    module: ova_deploy
    vcenter_props:
      vcenter_host: "{{ vcenter_host}}"
      vcenter_port: "{{ vcenter_port }}"
      vcenter_user: "{{ vcenter_user|urlencode }}"
      vcenter_password: "{{ vcenter_password|urlencode }}"
    location_props:
      resource_name: "{{ name }}"
      datacenter: "{{ datacenter }}"
      network: "{{ network }}"
      cluster: "{{ cluster }}"
      data_store: "{{ vra_datastore }}"
    ova_props:
      ova_directory: "{{ ova_location }}"
      ova_name: "{{ ova }}"
    additional_props:
     diskMode: 'thin'
     ipProtocol: 'IPv4'
    resource_props:
      varoot-password: "{{vra_root_password}}"
      va-ssh-enabled: "{{vra_ssh_enabled}}"
      vami.hostname: "{{vra_host_name}}"
    option_props:
      - powerOn
      - acceptAllEulas
      - allowExtraConfig
      - noSSLVerify

'''

class OVA(object):
    def __init__(self, module):
        self.module = module
        self.command = ["/usr/local/bin/ovftool/ovftool"]

    def execute_command(self, command):
        output,error = subprocess.Popen(command, universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        return output,error

    def append_command_with_list(self, opt_props):
        option_command=''
        for element in opt_props:
            option_command='--'+element
            self.command.append(option_command)
        return self.command

    def append_command_with_dict(self, dict_props):
        dict_command=''
        for key in dict_props:
            dict_command='--'+key+'=' + dict_props[key]
            self.command.append(dict_command)
        return self.command

    def append_command_with_instance_params(self, res_props):
        res_command=''
        for key in res_props:
            res_command='--prop:'+key+'= ' + res_props[key]
            self.command.append(res_command)
        return self.command

    def append_command_with_vcenter_params(self, vcenter_props, loc_props):
        vcenter_command= ["vi://" ,"vcenter_user", ":","vcenter_password", "@","vcenter_host", "/", "datacenter_name", "/", "host", "/", "vra_cluster", "/"]
        vcenter_command[1]= vcenter_props['vcenter_user']
        vcenter_command[3]= vcenter_props['vcenter_password']
        vcenter_command[5]= vcenter_props['vcenter_host']
        vcenter_command[7]= loc_props['datacenter']
        vcenter_command[11]= loc_props['cluster']
        self.command.append(''.join(vcenter_command))
        return self.command

    def append_command_with_ova_params(self, ova_props,loc_props):
        ova_command=''
        network_command=''
        name_command=''
        data_store_command=''
        ova_command= ova_props['ova_directory'] + '/'+ ova_props['ova_name']
        network_command= "--network="+loc_props['network']
        name_command= "--name="+loc_props['resource_name']
        data_store_command= "--datastore="+loc_props['data_store']
        self.command.append(name_command)
        self.command.append(network_command)
        self.command.append(data_store_command)
        self.command.append(ova_command)
        return self.command

    def get_command(self):
        return self.command

def core(module):
    res_props = module.params.get("resource_props")
    loc_props = module.params.get("location_props")
    ov_props = module.params.get("ova_props")
    add_props = module.params.get("additional_props")
    opt_props = module.params.get("option_props")
    vcenter_props = module.params.get("vcenter_props")

    ova = OVA(module)
    try:
        ova.append_command_with_list(opt_props)
        ova.append_command_with_dict(add_props)
        ova.append_command_with_instance_params(res_props)
        ova.append_command_with_ova_params(ov_props,loc_props)
        command=ova.append_command_with_vcenter_params(vcenter_props,loc_props)
        output, error = ova.execute_command(command)
        return False,output
    except Exception as a:
        return True, dict(msg=str(a))

def main():
    module = AnsibleModule(
        argument_spec = dict(
            resource_props = dict(type='dict',required=True),
            additional_props = dict(type='dict',required=True),
            location_props = dict(type='dict',required=True),
            ova_props = dict(type='dict',required=True),
            vcenter_props = dict(type='dict',required=True),
            option_props = dict(type='list',required=True)
        )
    )

    try:
        fail, result  = core(module)
    except Exception as e:
        import traceback
        module.fail_json(msg = '%s: %s\n%s' %(e.__class__.__name__, str(e), traceback.format_exc()))
    if fail:
        module.fail_json(msg=result)
    else:
        module.exit_json(changed=True, msg=result)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()
