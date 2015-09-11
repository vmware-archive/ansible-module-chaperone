#!/usr/bin/env python

try:
    import json
except ImportError:
    import simplejson as json

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from xml.etree.ElementTree import Element, SubElement, tostring

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
except ImportError:
    print("failed=True msg='pyVmomi is required to run this module'")

import atexit
import ssl
import requests
import time
import paramiko

if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context


DOCUMENTATION = '''
module: setup
Short_description:
description:
    - NSX Configuration. This module is for configuring NSX manager appliance. This module will:
        Authenticate and sync nsx manager with vcenter
        syslog setup for nsx manager
        Host prep
        Create 3 vtep ip pools
        Create 3 Controllers
        Configure VXLAN
        Segement ID
        Transport Zone

        Module will return ansible custom fact with either state of task completed or dictionary of
        needed values for state of nsx/vcenter component

version_added: "0.1"
options:
    host:
        description:
            - Address to connect to the vCenter instance.
        required: True
        default: null
    login:
        description:
            - Username to login to vCenter instance.
        required: True
        default: null
    password:
        description:
            - Password to authenticate to vCenter instance.
        required: True
        default: null
    port:
        description:
            - Port to access vCenter instance.
        required: False
        default: 443

    datacenter:
        description:
            - Dictionary containing the datacenter infomation
        required: True
        default:
    nsxcomponents:
        description:
            - Dictionary containing ippool information for module
        required: True
        default:
    nsxapi:
        description:
            - Dictionary containing the nsx api calls for this module
        required: True
        default:
    tmpfile:
        description:
            - Temporary file used to build and then parse xml
        required: True
        default:
    nsxoptions:
        description:
            - Dictionary containing boolean parameters for using module for specific function
            should only specify one True parameter to return corresponding modules functions custom
            ansible fact specified in that part of the module
        required: True
        default:


requirements: [ "pyVmomi", "requests", "atexit" ]
author: Jake Dupuy
'''

EXAMPLES = '''
- name: Create Controllers
  ignore_errors: no
  local_action:
    module: nsxconfig
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    datacenter: "{{ datacenter }}"
    nsxcomponents: "{{ nsx_components }}"
    nsxapi: "{{ nsx_api }}"
    tmpfile: "{{ tmpapifile }}"
    nsxoptions:
      getids: True
      get_ippool_ids: False
      ippool_state: False
      hostprep: False
      segment: False
      vdnscope: False
      vcsync: False
      controller: True
'''

class Vcenter(object):

    def __init__(self, module):
        self.module = module
        self.vsphere_host = module.params.get('host')
        login_user = module.params.get('login')
        login_password = module.params.get('password')
        self.port = module.params.get('port')
        self.datacenter_dict = module.params.get('datacenter')

        try:
            self.si = SmartConnect(host=self.vsphere_host, user=login_user, pwd=login_password, port=self.port)
        except:
            failmsg = "Could not connect to virtualserver: %s with: %s %s" \
                      % (self.vsphere_host, login_user, login_password)
            self.module.fail_json(msg=failmsg)

        atexit.register(Disconnect, self.si)

    @property
    def content(self):
        if not hasattr(self, '_content'):
            self._content = self.si.RetrieveContent()
        return self._content

    def get_target_object(self, vimtype, name=None, moid=None):

        limit = self.content.rootFolder
        container = self.content.viewManager.CreateContainerView(limit, vimtype, True)

        if name is not None and moid is None:
            for x in container.view:
                if x.name == name:
                    return x

        elif name and moid:
            object_moid = [str(x._moId) for x in container.view if x.name == name][0]
            return object_moid

        elif name is None and moid is None:
            return container.view
        return None

    def create_ids(self, vc_list, append_list, cluster=None):

        for i in vc_list:
            id_names = {}
            id_names.update({'name': i.name})
            id_names.update({'moid': str(i._moId)})

            if cluster:
                id_names.update({'resource_grp_id': str(i.resourcePool._moId)})

            append_list.append(id_names)

    def datacenter_data(self, dc):

        datacenter_info = {
            "cluster_info": [],
            "datastores": [],
            "vds_info": []
        }

        clusernames = [cluster for cluster in dc.hostFolder.childEntity]
        self.create_ids(clusernames, datacenter_info['cluster_info'], True)

        networks = dc.networkFolder.childEntity
        self.create_ids(networks, datacenter_info['vds_info'], None)

        datastores = dc.datastore
        self.create_ids(datastores, datacenter_info['datastores'], None)

        return datacenter_info

    def management_resgroup_vms(self, management_name, hostname=None):

        controller_vms = {}

        management_cluster = self.get_target_object([vim.ClusterComputeResource], management_name)

        if management_cluster:
            resgroup_vms = management_cluster.resourcePool.vm

            if resgroup_vms:
                for vm in resgroup_vms:
                    controller_vmid = vm._moId
                    controller_name = vm.name
                    controller_vms.update({controller_name: {}})
                    controller_vms[controller_name].update({'moid': controller_vmid})

                    if hostname:
                        controller_ip = vm.summary.guest.ipAddress
                        controller_vms[controller_name].update({'controller_ip': controller_ip})

                return controller_vms
            else:
                return controller_vms
        else:
            self.module.fail_json(msg="Could Not get Management Cluster")

    def wait_for_task(self, task):
        while task.info.state == vim.TaskInfo.State.running:
            time.sleep(4)
        failed = False
        if task.info.state == vim.TaskInfo.State.success:
            out = '"%s" completed successfully.%s' % \
                  (task.info.task, ':%s' % task.info.result if task.info.result else '')
        else:
            failed = True
            out = '%s did not complete successfully: %s' % (task.info.task, task.info.error.msg)

        return failed, out


class Nsx(object):
    def __init__(self, module):
        self.module = module
        self.nsxapi = module.params.get('nsxapi')
        self.nsxmanager = self.nsxapi['nsxip']
        self.nsx_user = self.nsxapi['nsx_user']
        self.nsx_password = self.nsxapi['nsx_password']
        self.apicall = self.nsxapi['nsx_ippools_all']
        self.ipidcall = self.nsxapi['nsx_ippools_id']
        self.nsx_cntrl = self.nsxapi['nsx_controller_api']
        self.rheaders = {'Content-Type': 'application/xml'}
        self.mgr = self.nsxapi['nsxhttp']
        self.tempfile = module.params.get('tmpfile')

    def vcsync_state(self):
        pass

    def get_tree(self, url, USER, PASS, rheaders, tempfile):
        try:
            r = requests.get(url, auth=(USER, PASS), verify=False, headers=rheaders)

            with open(tempfile, 'wb') as fd:
                for chunk in r.iter_content():
                    fd.write(chunk)

            tree = ET.ElementTree(file=tempfile)

            return tree

        except Exception as e:
            self.module.fail_json(msg="Failed to get tree: %s" % e)

    def make_lists(self, tree):
        try:

            ids = [elmid.text for elmid in tree.iterfind('ipamAddressPool/objectId')]
            pool_names = [elm.text for elm in tree.iterfind('ipamAddressPool/name')]

            return ids, pool_names

        except Exception as e:
            self.module.fail_json(msg="Failed to create lists: %s" % e)

    def ippool_data(self, ansible_varname):
        url = self.mgr + self.nsxmanager + self.apicall
        tree = self.get_tree(url, self.nsx_user,
                             self.nsx_password,
                             self.rheaders, self.tempfile)

        ids, poolnames = self.make_lists(tree)

        pool_data = {
            ansible_varname: []
        }

        for id in ids:
            single_pool_data = {}
            new_url = self.mgr + self.nsxmanager + self.ipidcall + id

            ntree = self.get_tree(new_url, self.nsx_user,
                                  self.nsx_password, self.rheaders,
                                  self.tempfile)

            container_ips = ntree.find('ipRanges')

            for elem in container_ips:
                startaddr = elem.findtext('startAddress')
                endaddr = elem.findtext('endAddress')

                single_pool_data.update({'range_start': startaddr})
                single_pool_data.update({'range_end': endaddr})

            for e in ntree.iterfind('name'):
                pool_name = e.text
                single_pool_data.update({'name': pool_name})
                single_pool_data.update({'moid': id})

            for g in ntree.iterfind('gateway'):
                gateway = g.text
                single_pool_data.update({'gateway': gateway})

            pool_data[ansible_varname].append(single_pool_data)

        return pool_data

    def check_lists(self, existing_list, desired_dict):

        existing_names = [name for i in existing_list for key, name in i.items() if key == 'name']

        desired_names = []

        for k, v in desired_dict.items():
            if k == 'ippools':
                for i in v:
                    for ipkey, dname in i.items():
                        if ipkey == 'name':
                            desired_names.append(dname)

        to_create = [m for m in desired_names if m not in existing_names]

        return to_create

    def segment_state(self):

        segment_dict = {}

        url = self.mgr + self.nsxmanager + self.nsxapi['nsx_segment']

        tree = self.get_tree(url, self.nsx_user,
                             self.nsx_password,
                             self.rheaders,
                             self.tempfile)

        root = tree.getroot()

        for elm in root.iter('segmentRange'):
            if elm:
                id = elm.find('id').text
                range_start = elm.find('begin').text
                range_end = elm.find('end').text
                name = elm.find('name').text

                segment_dict.update({'name': name})
                segment_dict.update({'id': id})
                segment_dict.update({'range_start': range_start})
                segment_dict.update({'range_end': range_end})

        return segment_dict

    def vdnscope_state(self):

        vdnscope_dict = {}

        url = self.mgr + self.nsxmanager + self.nsxapi['nsx_vdnscope']

        tree = self.get_tree(url, self.nsx_user,
                             self.nsx_password,
                             self.rheaders,
                             self.tempfile)

        root = tree.getroot()

        for elm in root.iter('vdnScope'):
            if elm:
                moid = elm.find('objectId').text
                name = elm.find('name').text
                id = elm.find('id').text

                vdnscope_dict.update({'moid': moid})
                vdnscope_dict.update({'name': name})
                vdnscope_dict.update({'id': id})

        return vdnscope_dict

    def vdn_post(self, load):

        url = self.mgr + self.nsxmanager + self.nsxapi['nsx_vdnscope']

        r = requests.post(url, auth=(self.nsx_user, self.nsx_password),
                              verify=False, data=load, headers=self.rheaders)

        content = r.content
        status = r.status_code

        if status != 201:
            msg = "FAILED creating vdnscope STATUS--> %s MSG--> %s" % (status, content)
            self.module.fail_json(msg=msg)
        else:
            return status

    def create_controller(self, controller_values):
       try:
            top = Element('controllerSpec')

            for key, val in controller_values.items():
                child = SubElement(top, key)
                child.text = val

            load = tostring(top)

            url = self.mgr + self.nsxmanager + self.nsx_cntrl

            r = requests.post(url, auth=(self.nsx_user, self.nsx_password),
                              verify=False, data=load, headers=self.rheaders)

            content = r.content
            status = r.status_code

            if status != 201:
                msg = "FAILED creating Controller STATUS--> %s MSG--> %s" % (status, content)
                self.module.fail_json(msg=msg)
            else:
                return content

       except Exception as e:
           self.module.fail_json(msg=str(e))

    def controller_values(self, target_data, target_key, target_name, target_inner_key):

       for k, v in target_data.items():
            if k == target_key:
                for i in v:
                    for key, val in i.items():
                        if val == target_name:
                            return i[target_inner_key]

    def set_controller_values(self, dcdata, ipdata, name):

        mgmt_resgrpid = self.controller_values(dcdata, 'cluster_info',
                                               self.nsxapi['nsxcontroller_cluster'],
                                               'resource_grp_id')
        dsinfo = self.controller_values(dcdata, 'datastores',
                                        self.nsxapi['nsxcontroller_ds'], 'moid')
        mgmt_pg = self.controller_values(dcdata, 'vds_info',
                                         self.nsxapi['nsxmgmtpg'], 'moid')
        ippoolid = self.controller_values(ipdata, 'ippool_info',
                                          self.nsxapi['nsxcontroller_pool'], 'moid')

        controller_xml_vals = {
            'name': name,
            'description': name,
            'ipPoolId': ippoolid,
            'resourcePoolId': mgmt_resgrpid,
            'datastoreId': dsinfo,
            'deployType': self.nsxapi['nsxcontroller_size'],
            'networkId': mgmt_pg,
            'password': self.nsxapi['nsxcontroller_pw'],
        }

        return controller_xml_vals

    def query_controller(self, jobid):
        try:
            controller_status = {}

            url = self.mgr + self.nsxmanager + self.nsxapi['nsxjob_status'] + jobid

            r = requests.get(url, auth=(self.nsx_user, self.nsx_password),
                              verify=False, headers=self.rheaders)

            statuscode = r.status_code

            if statuscode == 200:

                with open(self.tempfile, 'wb') as fd:
                    for chunk in r.iter_content():
                        fd.write(chunk)

                tree = ET.ElementTree(file=self.tempfile)

                root = tree.getroot()

                if root:
                    for elm in root.iter('controllerDeploymentInfo'):
                        if elm:
                            status = elm.findtext('status')
                            controller_status.update({'status': status})

                            vmid = elm.findtext('vmId')
                            if vmid:
                                controller_status.update({'moid': vmid})


                    return controller_status
                else:
                    self.module.fail_json(msg="Failed to get controller status Job id")

            else:
                self.module.fail_json(msg="Controller query-->STATUS was not 200")


        except Exception as e:
            self.module.fail_json(msg=str(e))

    def controller_join_status(self, controller_ip):

        cmd = "show control-cluster status"
        target = "Join complete"

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.WarningPolicy())

        try:
            ssh.connect(controller_ip, 22, self.nsxapi['nsx_user'], self.nsxapi['nsxcontroller_pw'])
        except Exception as e:
            self.module.fail_json(msg="ERROR: %s" % str(e))

        output = ""
        stdin, stdout, stderr = ssh.exec_command(cmd)

        stdout = stdout.readlines()
        ssh.close()

        for line in stdout:
            if target in line:
                return False

        if output != "":
            return True
        else:
            return True

    def wait_task(self, jobid):

        job_status = self.query_controller(jobid)

        while job_status['status'] != 'Failure':
            time.sleep(5)
            job_status = self.query_controller(jobid)

            if job_status['status'] == 'Success':
                failed = False
                return failed, job_status

            if job_status['status'] == 'Failure':
                failed = True
                return failed, job_status

    def create_controllers(self, loop_index, dc_data, ippool_data):

        controller_state = {}

        controller_elements = self.set_controller_values(dc_data, ippool_data,
                                                        self.nsxapi['nsxcontroller_name'] + str(loop_index))

        job_id = self.create_controller(controller_elements)

        task_status, controller_stats = self.wait_task(str(job_id))

        if not task_status:
            created = controller_stats['status']
            name = self.nsxapi['nsxcontroller_name'] + str(loop_index)
            controller_state.update({'name': name})
            controller_state.update({'state': created})
        else:
            msg = "Failed to create controller: "
            controller_state.update({'msg': msg})

        return controller_state


def core(module):

    nsxcomponents = module.params.get('nsxcomponents')
    nsxoptions = module.params.get('nsxoptions')

    get_ids = nsxoptions['getids']
    getip_poolids = nsxoptions['get_ippool_ids']
    ippool_state = nsxoptions['ippool_state']
    hostprep = nsxoptions['hostprep']
    segment = nsxoptions['segment']
    vdnscope = nsxoptions['vdnscope']
    vcsync = nsxoptions['vcsync']
    controller = nsxoptions['controller']

    if get_ids:
        v = Vcenter(module)

        dcname = v.datacenter_dict['name']
        dc = v.get_target_object([vim.Datacenter], dcname)

        if dc:
            datacenter_data = v.datacenter_data(dc)

            return False, datacenter_data
        else:
            msg = "Failed to find Datacenter: %s" % dcname
            return True, msg

    if vcsync:
        nsx = Nsx(module)

        ansible_var = 'vcsync_info'

        vcsyn_data = {
            ansible_var: []
        }

        vcsync_info = nsx.vcsync_state()

        if vcsync_info:
            vcsyn_data[ansible_var].append(vcsync_info)
        else:
            return False, vcsyn_data

        return False, vcsyn_data

    if getip_poolids or ippool_state:

        nsx = Nsx(module)

        ansible_var = 'ippool_info'
        state_dict = {}
        ippool_data = nsx.ippool_data(ansible_var)

        if getip_poolids and not ippool_state:
            return False, ippool_data

        if ippool_state and not getip_poolids:
            to_create = nsx.check_lists(ippool_data[ansible_var],nsxcomponents)

            state_dict.update({ansible_var: to_create})
            return False, state_dict

    if hostprep:

        v = Vcenter(module)
        nsx = Nsx(module)

        dcname = v.datacenter_dict['name']
        dc = v.get_target_object([vim.Datacenter], dcname)

        ansible_var = "cluster_state"

        cluster_data = {
            ansible_var: []
        }

        clusernames = [cluster for cluster in dc.hostFolder.childEntity]
        v.create_ids(clusernames, cluster_data[ansible_var])

        cluster_ids = []

        for i in cluster_data['cluster_state']:
            for k, v in i.items():
                if k == 'moid':
                    cluster_ids.append(v)

        for clusterid in cluster_ids:

            url = nsx.mgr + nsx.nsxmanager + nsx.nsxapi['nsx_hostprep'] + clusterid

            tree = nsx.get_tree(url, nsx.nsx_user,
                                nsx.nsx_password,
                                nsx.rheaders,
                                nsx.tempfile)
            root = tree.getroot()

            for x in root.iter('nwFabricFeatureStatus'):
                feature_id = x.find('featureId').text
                status = x.find('status').text

                if feature_id == 'com.vmware.vshield.firewall':
                    feature_id = 'vshield_firewall'
                elif feature_id == 'com.vmware.vshield.vsm.nwfabric.hostPrep':
                    feature_id = 'nwfabric_hostprep'
                elif feature_id == 'com.vmware.vshield.vsm.vdr_mon':
                    feature_id = 'vdr_mon'
                elif feature_id == 'com.vmware.vshield.vsm.messagingInfra':
                    feature_id = 'msginfra'
                elif feature_id == 'com.vmware.vshield.vsm.vxlan':
                    feature_id = 'vsm_vxlan'

                for c in cluster_data[ansible_var]:
                    if c['moid'] == clusterid:
                        c.update({feature_id: status})

        return False, cluster_data

    if segment:

        nsx = Nsx(module)

        ansible_var = 'segment_info'

        segment_data = {
            ansible_var: []
        }

        segment_info = nsx.segment_state()

        if segment_info:
            segment_data[ansible_var].append(segment_info)
        else:
            return False, segment_data

        return False, segment_data

    if vdnscope:

        nsx = Nsx(module)

        ansible_var = 'vdnscope_info'

        vdnscope_data = {
            ansible_var: []
        }

        vdnscope_info = nsx.vdnscope_state()

        if vdnscope_info:
            vdnscope_data[ansible_var].append(vdnscope_info)
        else:
            status = nsx.vdn_post(nsx.tempfile)
            vdnscope_data[ansible_var].append(status)

        return False, vdnscope_data

    if controller:

        v = Vcenter(module)
        nsx = Nsx(module)

        ansible_var = 'controller_info'
        controller_data = {
            ansible_var: []
        }

        dcname = v.datacenter_dict['name']
        dc = v.get_target_object([vim.Datacenter], dcname)

        if dc:
            dc_data = v.datacenter_data(dc)
            ippool_data = nsx.ippool_data('ippool_info')
        else:
            nsx.module.fail_json(msg="Cannot Find datacenter: %s" % dcname)

        existing_controllers = v.management_resgroup_vms(nsx.nsxapi['nsxcontroller_cluster'], True)

        if not existing_controllers:

            for i in range(3):
                controller_state = nsx.create_controllers(i, dc_data, ippool_data)

                controller_data[ansible_var].append(controller_state)

            return False, controller_data

        elif len(existing_controllers) < 3:
            controller_range = 3 - len(existing_controllers)

            for x in range(controller_range):
                controller_state = nsx.create_controllers(x, dc_data, ippool_data)

                controller_data[ansible_var].append(controller_state)

            return False, controller_data

        else:
            msg = "There are already 3 controllers installed"
            controller_data[ansible_var].append(msg)
            return False, controller_data


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            datacenter=dict(type='dict', required=True),
            nsxcomponents=dict(type='dict', required=True),
            nsxapi=dict(type='dict', required=True),
            tmpfile=dict(type='str', required=True),
            nsxoptions=dict(type='dict', required=True),
        ),
    )

    fail, result = core(module)

    if fail:
        module.fail_json(changed=False, msg=result)
    else:

        ansible_facts_dict = {
            "changed": False,
            "ansible_facts": {

            }
        }

        for key, val in result.items():
            ansible_facts_dict['ansible_facts'].update({key: val})

        ansible_facts_dict['changed'] = True

        print json.dumps(ansible_facts_dict)

from ansible.module_utils.basic import *
from ansible.module_utils.facts import *
main()
