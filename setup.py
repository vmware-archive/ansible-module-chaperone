#!/usr/bin/env python

try:
    import json
except ImportError:
    import simplejson as json

#from netaddr import *

import time
import atexit
import subprocess
import ssl
#import random

if hasattr(ssl, '_create_default_https_context') and hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
except ImportError:
    print("failed=True msg='pyVmomi is required to run this module'")

# todo configure hosts vmk0 mgmt vmk0 for static ip
# todo apply host profile for vmk0 static ip


DOCUMENTATION = '''
module: setup
Short_description: Create Datacenter, clusters, add/configure hosts, create hosts profiles
description:
    - Based on the various Boolean parameters for the module this module will:
     create datacenter and clusters,
    - Add a single reference host to each clusters or add a single host to a specified cluster.
    - Configure each reference host in each cluster on the vds, or a single specified host
    - Configure the reference hosts (or specified single host) taking the exsisting managment
    vmkernel adapter and add it to the management portgroup on the vds with the management service
    - Add vmkernel adapters for vmotion and storage adding them to the vmotion and storage
    portgroups on the vds with the vmotion service enabled on the vmotion vmkernel adapter
    - Create a host profile from each reference host in each cluster and attach the hostprofile
    to the corresponding cluster

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
            - An ansible dictionary describing the datacenter, cluster, host and vds
            information used for this module. The dictionary is placed in the roles
            defaults directory
        required: True
        example:
            datacenter:
              name: "{{ datacenter_name }}"
              clusters:
              - name: "{{ vio_cluster_mgmt }}"
                hosts:
                - name: "{{ host.name }}"
                  ip: "{{ host.ip }}"
                  mac: "{{ host.mac }}"
                  username: "{{ host.username }}"
                  password: "{{ host.password }}"
              - name: "{{ vio_cluster_edge }}"
                hosts:
                - name: "{{ host.name }}"
                  ip: "{{ host.ip }}"
                  mac: "{{ host.mac }}"
                  username: "{{ host.username }}"
                  password: "{{ host.password }}"
              - name: "{{ vio_cluster_compute }}"
                hosts:
                - name: "{{ host.name }}"
                  ip: "{{ host.ip }}"
                  mac: "{{ host.mac }}"
                  username: "{{ host.username }}"
                  password: "{{ host.password }}"
              vds:
                  name: "{{ vds_name }}"
                  portgroups:
                    api:
                    - name: "{{ api_grp }}"
                      servicetype:
                      cider:
                    management:
                    - name: "{{ mgmt_grp }}"
                      servicetype: 'management'
                      cider:
                    storage:
                    - name: "{{ store_grp }}"
                      servicetype:
                      cider: "{{ strg_cider }}"
                    vmotion:
                    - name: "{{ vmotion_grp }}"
                      servicetype: 'vmotion'
                      cider: "{{ vmo_cider }}"
                    external:
                    - name: "{{ ext_grp }}"
                      servicetype:
                      cider:
    esxhost:
        description:
            - An ansible dictionary used to describe the values for using module with
            single host
        required: True
        example:
            esxhost:
              name: "{{ host_ip_name }}"
              user: "{{ host_username }}"
              password: "{{ host_password }}"
              cluster: "{{ addhost_cluster }}"
    singlehost:
        description:
            - A variable set to yes/no for specifing to use module for multiple hosts
            or for single host
        required: False
        default: 'no'
    create_dc_clusters:
        description:
            - A boolean parameter used to specify if using the module for creating
            datacenter and clusters specified in the datacenter parameters dictionary
        required: True
        default: None
    add_hosts:
        description:
            - A boolean parameter used to specify if using the module for adding hosts
            as specified in the datacenter parameters dictionary or the esxhost dictionary
            for single host
        required: True
        default: None
    usehostname:
        description:
            - A boolean parameter used to specify to use dns hostname for adding/configuring
            hosts or single host
        required: False
        default: False
    config_hosts:
        description:
            - A boolean parameter used to specify if using the module to configure hosts
            or single host
        required: True
        default: None
    hostprofiles:
        description:
            - A boolean parameter used to specify if using the module to create host profiles
        required: True
        default: None
    apply_hostprofiles:
        description:
            - A boolean parameter used to specify if applying the previously created host profiles
        required: True
        default: None

requirements: [ "pyVmomi", "subprocess", "time", "atexit" ]
author: Jake Dupuy
'''

EXAMPLES = '''
- name: Create Datacenter and Clusters
  ignore_errors: no
  local_action:
    module: testing_dc
    host: "{{ vcenter_host }}"
    login: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    port: "{{ vcenter_port }}"
    datacenter: "{{ datacenter }}"
    esxhost: "{{ esxhost }}"
    singlehost: "{{ add_single_host }}"
    create_dc_clusters: True
    add_hosts: False
    usehostname: False
    config_hosts: False
    hostprofiles: False
'''

class Vcenter(object):

    def __init__(self, module):
        self.module = module
        self.vsphere_host = module.params.get('host')
        login_user = module.params.get('login')
        login_password = module.params.get('password')
        self.port = module.params.get('port')
        self.datacenter_dict = module.params.get('datacenter')
        self.esxhost = module.params.get('esxhost')
        self.datacenter_name = self.datacenter_dict['name']
        self.vds_name = self.datacenter_dict['vds']['name']
        self.portgroup_types = [pgtype for pgtype in self.datacenter_dict['vds']['portgroups'].iterkeys()]


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

    @property
    def dvs_manager(self):
        if not hasattr(self, '_dvs_manager'):
            self._dvs_manager = self.content.dvSwitchManager
        return self._dvs_manager

    @property
    def clusters_ips(self):
        if not hasattr(self, '_clusters_ips'):
            cluster_hosts = {}
            clusters = [c for c in self.datacenter_dict['clusters']]
            [cluster_hosts.update({c['name']:j['ip']}) for c in clusters for j in c['hosts']]
            self._clusters_ips = cluster_hosts
        return self._clusters_ips

    @property
    def clusters_dnsname(self):
        if not hasattr(self, '_clusters_dnsname'):
            cluster_hosts = {}
            clusters = [c for c in self.datacenter_dict['clusters']]
            [cluster_hosts.update({c['name']:j['name']}) for c in clusters for j in c['hosts']]
            self._clusters_dnsname = cluster_hosts
        return self._clusters_dnsname

    @property
    def clusters_names(self):
        if not hasattr(self, '_clusters_names'):
            self._clusters_names = [n for n in self.clusters_ips.iterkeys()]
        return self._clusters_names

    def get_target_object(self, vimtype, name=None):

        limit = self.content.rootFolder
        container = self.content.viewManager.CreateContainerView(limit, vimtype, True)

        if name is not None:
            for x in container.view:
                if x.name == name:
                    return x
        elif name is None:
            return container.view
        return None

    def check_object(self, vimtype, name):
        target_object = self.get_target_object(vimtype, name)
        if target_object is not None:
            return target_object
        return None

    def wait_for_task(self, task):
        while task.info.state == vim.TaskInfo.State.running:
            time.sleep(2)
        failed = False
        if task.info.state == vim.TaskInfo.State.success:
            out = '"%s" completed successfully.%s' % \
                  (task.info.task, ':%s' % task.info.result if task.info.result else '')
        else:
            failed = True
            out = '%s did not complete successfully: %s' % (task.info.task, task.info.error.msg)

        return failed, out

#####################################
### VDS Methods
#####################################

    def vds(self):
        try:
            vds = self.get_target_object([vim.DistributedVirtualSwitch], self.vds_name)

            if vds and isinstance(vds, vim.DistributedVirtualSwitch):
                return vds
            else:
                dc = self.get_target_object([vim.Datacenter], self.datacenter_name)
                if dc:
                    vds = [n for n in dc.networkFolder.childEntity \
                           if n.name == self.vds_name][0]

                    check = self.get_target_object([vim.DistributedVirtualSwitch], vds.name)

                    if isinstance(check, vim.DistributedVirtualSwitch) \
                        and isinstance(check, vim.DistributedVirtualSwitch):

                        return vds
                else:
                    self.module.fail_json(msg="cannot get vds")
        except Exception as e:
            self.module.fail_json(msg="Failed to get object")

    def vdsuuid(self):
        try:
            #this needs a state check and fail out
            vdsuuid = self.vds().uuid
            return vdsuuid
        except vmodl.fault as fault:
            self.module.fail_json(msg=fault.msg)

    def uplink_key(self):
        try:
            vds = self.vds()
            uplink_portgroup = vds.config.uplinkPortgroup

            #add check condition for returning index[0]
            uplink_key = [k.key for k in uplink_portgroup][0]

            return uplink_key

        except vmodl.fault as e:
            self.module.fail_json(msg=e.msg)

    def portgroup_keys(self, name=None, key=None):
        try:
            portgroup_name_keys = {}

            vds = self.vds()
            portgroups = vds.portgroup

            for portgroup in portgroups:
                portgroup_name_keys.update({portgroup.name: portgroup.key})

            if name is None and key is None:
                return portgroup_name_keys

            for portgroup_name, pg_key in portgroup_name_keys.items():
                if portgroup_name == name:
                    return pg_key
                elif pg_key == key:
                    return portgroup_name

        except Exception as e:
            self.module.fail_json(msg=str(e))

#####################################
### END VDS Methods
#####################################

class Datacenter(Vcenter):

    def check_dc(self):
        dc = self.get_target_object([vim.Datacenter], self.datacenter_name)
        if dc:
            return True, dc
        else:
            return False, None

    def create_datacenter(self):
        try:
            folder = self.content.rootFolder
            new_datacenter = folder.CreateDatacenter(name=self.datacenter_name)
            return new_datacenter
        except vim.fault.DuplicateName as duplicate_name:
            self.module.fail_json(msg=duplicate_name.msg)
        except (vim.fault.InvalidName, vmodl.fault.NotSupported) as e:
            self.module.fail_json(msg=e.msg)


class Cluster(Vcenter):

    @staticmethod
    def create_configspec():
        default_vmsettings = vim.cluster.DasVmSettings(restartPriority="high")
        das_config = vim.cluster.DasConfigInfo(enabled=True,
                                               admissionControlEnabled=True,
                                               failoverLevel=1,
                                               hostMonitoring="enabled",
                                               vmMonitoring="vmAndAppMonitoring",
                                               defaultVmSettings=default_vmsettings)
        drs_config = vim.cluster.DrsConfigInfo(enabled=True,
                                               defaultVmBehavior="fullyAutomated")
        cluster_config = vim.cluster.ConfigSpecEx(dasConfig=das_config,
                                                  drsConfig=drs_config)
        return cluster_config

    def cluster_check(self, dc):
        current_clusters = [cluster.name for cluster in dc.hostFolder.childEntity]
        need_to_add = [s for s in self.clusters_names if s not in current_clusters]

        if need_to_add:
            return True, need_to_add
        else:
            return False, None

    def create_clusters(self, single_cluster_name=None):
        try:
            cluster_spec = self.create_configspec()
            dc = self.get_target_object([vim.Datacenter], self.datacenter_name)

            if isinstance(dc, vim.Datacenter):
                host_folder = dc.hostFolder
                status, to_add = self.cluster_check(dc)

                if single_cluster_name is None and not status:
                    clusters = [host_folder.CreateClusterEx(name=cluster_name, spec=cluster_spec) \
                                for cluster_name in self.clusters_names]
                    clusternames = [c.name for c in clusters]
                    return clusternames

                elif status:
                    clusters = [host_folder.CreateClusterEx(name=cluster_name, spec=cluster_spec) \
                                for cluster_name in to_add]
                    clusternames = [c.name for c in clusters]
                    return clusternames

                if single_cluster_name is not None:
                    cluster = host_folder.CreateClusterEx(name=single_cluster_name, spec=cluster_spec)
                    return cluster.name
            else:
                failmsg = "Datacenter %s not present" % self.datacenter_name
                self.module.fail_json(msg=failmsg)

        except (vim.fault.DuplicateName,
                vmodl.fault.InvalidArgument,
                vim.fault.InvalidName) as error:
            self.module.fail_json(msg=error.msg)


class Hosts(Vcenter):

#####################################
### Add Hosts Methods
#####################################

    def get_host_sha1(self, hostipname):
        try:
            cmd_start = "echo -n | openssl s_client -connect "
            cmd_ip = hostipname
            cmd_end = ":443 2>/dev/null | openssl x509 -noout -fingerprint -sha1 | awk -F = '{print $2}'"

            cmd = cmd_start + cmd_ip + cmd_end
            output = subprocess.check_output(cmd, shell=True)
            host_sha1 = output.rstrip('\n')
            return host_sha1
        except subprocess.CalledProcessError as e:
            self.module.fail_json(msg=str(e))

    def get_sha(self, datacenter, hostname, username, password, sslthumprint=None):
        try:
            if not sslthumprint:
                datacenter.QueryConnectionInfo(hostname, -1, username, password)
            elif sslthumprint:
                connectioninfo = datacenter.QueryConnectionInfo(hostname, -1, username, password, sslthumprint)
                return connectioninfo
        except vim.fault.SSLVerifyFault as ssl:
            return ssl.thumbprint
        except Exception as error:
            self.module.fail_json(msg=error.msg)

    def hostspec(self, host_name, sslprint, hostusername, hostpassword):
        hostconnectspec = vim.host.ConnectSpec(hostName=host_name,
                                               sslThumbprint=sslprint,
                                               userName=hostusername,
                                               password=hostpassword)
        return hostconnectspec

    def addhost(self, cluster, hostspec):
        try:
            add_host_task = cluster.AddHost(spec=hostspec, asConnected=True)
            return add_host_task
        except vmodl.MethodFault as e:
            self.module.fail_json(msg=e.msg)

    def check_host(self, host_name):
        host = self.get_target_object([vim.HostSystem], host_name)
        if host:
            return True
        else:
            return False

    def add_single_host(self, cluster_name, host_ip, singlehost=None):
        try:
            if singlehost:
                hostusername = self.esxhost['user']
                hostpassword = self.esxhost['password']
            else:
                hostusername, hostpassword = self.get_hosts_unpw(cluster_name)

            host_sha = self.get_host_sha1(host_ip)
            host_spec = self.hostspec(host_ip, host_sha, hostusername, hostpassword)
            cluster = self.get_target_object([vim.ClusterComputeResource], cluster_name)
            add_host = self.addhost(cluster, host_spec)

            return add_host
        except Exception as e:
            self.module.fail_json(str(e))

    def get_hosts_unpw(self, clustername):
        hostinfo = [c['hosts'] for c in self.datacenter_dict['clusters'] if c['name'] == clustername][0]

        username = [v for i in hostinfo for k, v in i.items() if k == 'username'][0]

        password = [v for i in hostinfo for k, v in i.items() if k == 'password'][0]

        return username, password

    def add_hosts_clusters(self, esxhost=None, cluster=None, dnsname=None):
        cluster_status = {}

        if not esxhost and not cluster:

            if dnsname:
                clusters_add = self.clusters_dnsname
            else:
                clusters_add = self.clusters_ips

            for cluster_name, host in clusters_add.items():

                if not self.check_host(host):

                    add_host_task = self.add_single_host(cluster_name, host)
                    failed, task_msg = self.wait_for_task(add_host_task)

                    if failed:
                        self.module.fail_json(msg=task_msg)
                    else:
                        status = "FAILED: %s" % failed
                        cluster_status.update({status: task_msg})
                        continue
                else:
                    message = "HOST: %s already added to CLUSTER: %s" % (host, cluster_name)
                    cluster_status.update({"MESSAGE": message})
            return False, cluster_status

        if esxhost and cluster:

            if not self.check_host(esxhost):
                add_host_task = self.add_single_host(cluster, esxhost, True)
                failed, task_msg = self.wait_for_task(add_host_task)
                return failed, task_msg
            else:
                message = "Host %s already added" % esxhost
                return True, message

#####################################
### Host configuration methods
#####################################

    def host_compatibility(self, host, vds, dc):

        try:
            compatible_hosts = self.dvs_manager.QueryCompatibleHostForExistingDvs(dc, True, vds)

            if host in compatible_hosts:
                return True
            else:
                return False

        except vmodl.fault.InvalidArgument as invalid_arg:
            self.module.fail_json(msg=invalid_arg.msg)
        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)

    def vswitch_remove(self, name):

        host = self.get_target_object([vim.HostSystem], name)

        if isinstance(host, vim.HostSystem):
            host_configmanager = getattr(host, 'configManager')

            net_config = host_configmanager.networkSystem.networkConfig

            vswitch = [s.name for s in net_config.vswitch][0]
            numports = [s.spec.numPorts for s in net_config.vswitch][0]

            return vswitch, numports
        else:
            message = "Could not find host: %s" % name
            self.module.fail_json(msg=message)

    def host_pnic(self, name):

        host = self.get_target_object([vim.HostSystem], name)

        if isinstance(host, vim.HostSystem):

            host_config = getattr(host, 'config')
            pnics = [p.device for p in host_config.network.pnic \
                     if p.device == "vmnic0"][0]

            return pnics

        else:
            message = "Could not find host: %s" % name
            self.module.fail_json(msg=message)

    def host_vmkernel(self, name):

        host = self.get_target_object([vim.HostSystem], name)

        if isinstance(host, vim.HostSystem):
            host_configmanager = getattr(host, 'configManager')

            virt_nic_manager = host_configmanager.virtualNicManager

            try:
                management_vnic = virt_nic_manager.QueryNetConfig("management")

                portgroup = [i.portgroup for i in management_vnic.candidateVnic][0]
                device = [j.device for j in management_vnic.candidateVnic][0]

                return portgroup, device

            except (vim.fault.HostConfigFault, vmodl.fault.InvalidArgument) as e:
                self.module.fail_json(msg=e.msg)

        else:
            message = "Could not find host: %s" % name
            self.module.fail_json(msg=message)

#####################################
### Host configuration specs
#####################################

    def reconfigure_vds_task(self, vds, host):
        try:
            reconfig_vds_spec = self.build_reconfigure_vds(vds, host)

            reconfig_task = vds.ReconfigureDvs_Task(reconfig_vds_spec)
            failed, task_msg = self.wait_for_task(reconfig_task)

            return failed, task_msg

        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)

    def management_port_key(self):

        management_name, servicetype, ciderblock = \
            self.portgroup_name_servicetype('management')

        management_key = self.portgroup_keys(management_name, None)
        return management_key

    def check_host_proxyswitch(self, host):
        try:
            netinfo = host.configManager.networkSystem.networkInfo

            target_types = ['management', 'vmotion', 'storage']
            target_names = [j['name'] for i in target_types for j in self.datacenter_dict['vds']['portgroups'][i]]
            target_pg_keys = [self.portgroup_keys(name, None) for name in target_names]

            if hasattr(netinfo, 'proxySwitch'):
                proxy_switches = getattr(netinfo, 'proxySwitch')

                if proxy_switches:
                    checkuuid = [p.dvsUuid for p in proxy_switches if p.dvsName == self.vds_name][0]
                else:
                    return False, None

                if checkuuid == self.vdsuuid():
                    vnics_pg_keys = [v.spec.distributedVirtualPort.portgroupKey for v in netinfo.vnic]

                    missing = [pg_key for pg_key in target_pg_keys if pg_key not in vnics_pg_keys]

                    if missing:
                        return False, missing
                    else:
                        return True, None

        except vmodl.fault as fault:
            self.module.fail_json(msg=fault)

    def add_vmkerel_adapter(self, host, portgroup_name, ip=None, mask=None, service_type=None):

        pgkey = self.portgroup_keys(portgroup_name, None)

        if isinstance(host, vim.HostSystem):
            config_manager = getattr(host, 'configManager')

            vmk_spec = self.build_add_vmk(pgkey, self.vdsuuid(), ip, mask)

            try:
                new_vmk = config_manager.networkSystem.AddVirtualNic("", vmk_spec)

                if service_type:
                    config_manager.virtualNicManager.SelectVnicForNicType(service_type, new_vmk)

            except (vim.fault.HostConfigFault, vmodl.fault.InvalidArgument,
                    vim.fault.AlreadyExists, vim.fault.ResourceInUse) as fault:
                self.module.fail_json(msg=fault.msg)

        if new_vmk:
            return False, new_vmk
        else:
            return True, None

    def portgroup_name_servicetype(self, vio_portgroup_type):

        if vio_portgroup_type in self.portgroup_types:
            portgroups = self.datacenter_dict['vds']['portgroups'][vio_portgroup_type]

            portgroup_name = [v for i in portgroups for k, v in i.items() if k == 'name'][0]
            servicetype = [v for i in portgroups for k, v in i.items() if k == 'servicetype'][0]
            ciderblock = [v for c in portgroups for k, v in c.items() if k == 'cider'][0]

            check = self.get_target_object([vim.DistributedVirtualPortgroup], portgroup_name)

            if check:
                return check.name, servicetype, ciderblock
            else:
                return portgroup_name, None, None
        else:
            self.module.fail_json(msg="not valid pg type")

    def add_vmk(self, host, portgroup_type, ip=None, mask=None):

        portgroup_name, servicetype, ciderblock = \
            self.portgroup_name_servicetype(portgroup_type)

        status, vmk = self.add_vmkerel_adapter(host, portgroup_name, ip, mask, servicetype)

        return status, vmk

    def add_missing_vmk(self, host, portgroup_key):

        portgroup_name = self.portgroup_keys(None, portgroup_key)

        pg_type = [k for k, v in self.datacenter_dict['vds']['portgroups'].items()\
                   for i in v if i['name'] == portgroup_name][0]

        status, vmk = self.add_vmk(host, pg_type)

        return status, vmk

    def create_host_profile(self, hostprofile_spec):
        try:

            hostprofile_manager = self.content.hostProfileManager
            create_profile = hostprofile_manager.CreateProfile(createSpec=hostprofile_spec)

            if create_profile:
                return False, create_profile
            else:
                return True, None

        except vmodl.MethodFault as method_fault:
            self.module.fail_json(msg=method_fault.msg)
        except vmodl.RuntimeFault as runtime_fault:
            self.module.fail_json(msg=runtime_fault.msg)

    def check_hostprofile(self, vim_host, profilename):

        profiles = self.content.hostProfileManager.profile

        if profiles:
            profile_check = [p.name for p in profiles]

            if profilename in profile_check:
                profile = [p for p in profiles if p.name == profilename][0]

                cluster_check = (vim_host.parent in profile.entity)

                return cluster_check, True

            else:
                return False, False
        else:
            return False, False

    def add_hostprofile_cluster(self, host):

        vim_host = self.get_target_object([vim.HostSystem], host)

        profile_name = str(vim_host.parent.name) + '_profile'

        attached_cluster, profile_present = self.check_hostprofile(vim_host, profile_name)

        if not attached_cluster and not profile_present:

            spec_status, profile_spec = self.build_host_profilespec(profile_name, vim_host)

            if not spec_status:
                status, hostprofile = self.create_host_profile(profile_spec)

                hostprofile.UpdateReferenceHost(vim_host)

                hostprofile.AssociateProfile([vim_host.parent])

                attached_cluster, profile_present = \
                    self.check_hostprofile(vim_host, profile_name)

                if attached_cluster and profile_present:
                    message = "Created profile: %s Attached to cluster: %s" % (hostprofile.name, vim_host.parent.name)
                    return False, message

        elif profile_present and not attached_cluster:

            hostprofile = [p for p in self.content.hostProfileManager.profile \
                           if p.name == profile_name][0]

            hostprofile.AssociateProfile([vim_host.parent])

            attached_cluster, profile_present = self.check_hostprofile(vim_host, profile_name)

            if attached_cluster and profile_present:
                return False, "attached to cluster"

        else:
            return True, "already have profile and attached to cluster"

    def get_host_current_netinfo(self, host):

        virtnic_manager = host.configManager.virtualNicManager

        management_vnic = virtnic_manager.QueryNetConfig("management")

        vnic = [n for n in management_vnic.candidateVnic][0]

        ip_addr = vnic.spec.ip.ipAddress
        netmask = vnic.spec.ip.subnetMask

        return ip_addr, netmask

    def update_deferredparam(self, host, execute_result, hostprofile):

        required_input = execute_result.requireInput
        ip_addr, netmask = self.get_host_current_netinfo(host)

        for keyanyval in required_input[0].parameter:
            if isinstance(keyanyval, vmodl.KeyAnyValue):
                if keyanyval.key == 'address':
                    keyanyval.value = ip_addr
                if keyanyval.key == 'subnetmask':
                    keyanyval.value = netmask

        execute_result_param = hostprofile.ExecuteHostProfile(host, required_input)

        return execute_result_param

    def check_maintenance_mode(self, host):

        mode = host.runtime.inMaintenanceMode

        if not mode:
            enter_maintenace_mode = host.EnterMaintenanceMode(0, True)

            failed, task_msg = self.wait_for_task(enter_maintenace_mode)

            if not failed:
                return True
            else:
                return False
        else:
            return True

    def apply_hostprofile(self, host):

        profile_manager = self.content.hostProfileManager

        vim_host = self.get_target_object([vim.HostSystem], host)

        hostprofile = [p for p in profile_manager.profile for i in p.entity if i == vim_host.parent][0]

        execute_result = hostprofile.ExecuteHostProfile(vim_host)

        if execute_result.status == 'success':

            spec = execute_result.configSpec

            apply_task = profile_manager.ApplyHostConfig_Task(vim_host, spec)

            failed, task_msg = self.wait_for_task(apply_task)

            return failed, task_msg

        elif execute_result.status =='needInput':

            execute_result_param = self.update_deferredparam(vim_host, execute_result, hostprofile)

            if execute_result_param.status == 'success':

                spec = execute_result_param.configSpec

                apply_task = profile_manager.ApplyHostConfig_Task(vim_host, spec)

                failed, task_msg = self.wait_for_task(apply_task)

                return failed, task_msg

        elif execute_result.error:
            return True, execute_result.error
        else:
            self.module.fail_json(msg="Failed to apply host profile")

    def build_vswitch_spec(self, host_vswitch_name, num_ports):
        try:
            policy_shaping = vim.host.NetworkPolicy.TrafficShapingPolicy(enabled=False)

            policy_offload = vim.host.NetOffloadCapabilities(csumOffload=True,
                                                             tcpSegmentation=True,
                                                             zeroCopyXmit=True)

            fail_spec = vim.host.NetworkPolicy.NicFailureCriteria(checkSpeed="minimum",
                                                                  speed=10,
                                                                  checkDuplex=False,
                                                                  fullDuplex=False,
                                                                  checkErrorPercent=False,
                                                                  percentage=0,
                                                                  checkBeacon=False)

            policy_teaming = vim.host.NetworkPolicy.NicTeamingPolicy(policy="loadbalance_srcid",
                                                                     reversePolicy=True,
                                                                     notifySwitches=True,
                                                                     rollingOrder=False,
                                                                     failureCriteria=fail_spec)

            policy_sec = vim.host.NetworkPolicy.SecurityPolicy(allowPromiscuous=False,
                                                               macChanges=True,
                                                               forgedTransmits=True)

            vswitch_policy = vim.host.NetworkPolicy(security=policy_sec,
                                                    nicTeaming=policy_teaming,
                                                    offloadPolicy=policy_offload,
                                                    shapingPolicy=policy_shaping)

            vswitch_spec = vim.host.VirtualSwitch.Specification(numPorts=num_ports,
                                                                policy=vswitch_policy)

            vswitch_config = vim.host.VirtualSwitch.Config(changeOperation="edit",
                                                           name=host_vswitch_name,
                                                           spec=vswitch_spec)
            return vswitch_config
        except Exception as e:
            self.module.fail_json(msg="FAILED to buil vswitch spec %s" % str(e))

    def build_host_proxy_config(self, pnic_device, vds_uuid, uplink_key):
        try:
            host_pnic_spec = vim.dvs.HostMember.PnicSpec(pnicDevice=pnic_device,
                                                         uplinkPortgroupKey=uplink_key)

            host_backing = vim.dvs.HostMember.PnicBacking(pnicSpec=[host_pnic_spec])

            proxy_spec = vim.host.HostProxySwitch.Specification(backing=host_backing)

            proxy_config = vim.host.HostProxySwitch.Config(changeOperation="edit",
                                                           uuid=vds_uuid,
                                                           spec=proxy_spec)
            return proxy_config
        except Exception as e:
            self.module.fail_json(msg="FAILED to build proxy spec %s" % str(e))

    def build_port_group_config(self, vswitch_name):
        try:
            portgroup_spec_policy = vim.host.NetworkPolicy()

            portgroup_spec = vim.host.PortGroup.Specification(name=vswitch_name,
                                                              vlanId=-1,
                                                              vswitchName="",
                                                              policy=portgroup_spec_policy)

            portgroup_config = vim.host.PortGroup.Config(changeOperation="remove",
                                                         spec=portgroup_spec)
            return portgroup_config

        except Exception as e:
            self.module.fail_json(msg="FAILED to build portgroup spec %s" % str(e))

    def build_vnic_config(self, vds_uuid, target_vmknic, target_portgroup_key):
        try:
            vds_port_config = vim.dvs.PortConnection(switchUuid=vds_uuid,
                                                     portgroupKey=target_portgroup_key)

            vnic_config_spec = vim.host.VirtualNic.Specification(distributedVirtualPort=vds_port_config)

            vnic_config = vim.host.VirtualNic.Config(changeOperation="edit",
                                                     device=target_vmknic,
                                                     spec=vnic_config_spec)
            return vnic_config
        except Exception as e:
            return dict(msg="ERROR vnic config--> %s" % e)

    def build_reconfigure_vds(self, target_vds, target_host):
        try:
            vds_spec = vim.DistributedVirtualSwitch.ConfigSpec()
            vds_spec.configVersion = target_vds.config.configVersion
            vds_spec_host = vim.dvs.HostMember.ConfigSpec()
            vds_spec_host.operation = "add"
            vds_spec_host.host = target_host
            vds_spec.host = [vds_spec_host]
            return vds_spec
        except Exception as e:
            self.module.fail_json(msg="ERRROR Reconfiguring vds--> %s" % e)

    def build_host_netconfig(self, host, vdsuuid, uplink_key, management_key):

        vswitch, numports = self.vswitch_remove(host)
        pnic = self.host_pnic(host)
        portgroup_remove, vmk_adapter = self.host_vmkernel(host)

        vswitch_spec = self.build_vswitch_spec(vswitch, numports)
        proxy_spec = self.build_host_proxy_config(pnic, vdsuuid, uplink_key)
        portgroup_spec = self.build_port_group_config(portgroup_remove)
        vnic_spec = self.build_vnic_config(vdsuuid, vmk_adapter, management_key)

        host_netconfig = vim.host.NetworkConfig(vswitch=[vswitch_spec],
                                                proxySwitch=[proxy_spec],
                                                portgroup=[portgroup_spec],
                                                vnic=[vnic_spec])
        if host_netconfig:
            return False, host_netconfig
        else:
            return True, None

    def build_add_vmk(self, pg_key, vdsuuid, ip_addr=None, net_mask=None):
        try:
            ipv6_spec = vim.host.IpConfig.IpV6AddressConfiguration(autoConfigurationEnabled=False,
                                                                   dhcpV6Enabled=False)

            if ip_addr and net_mask:
                ip_spec = vim.host.IpConfig(dhcp=False,
                                            ipAddress=ip_addr,
                                            subnetMask=net_mask,
                                            ipV6Config=ipv6_spec)
            else:
                ip_spec = vim.host.IpConfig(dhcp=True,
                                            ipV6Config=ipv6_spec)

            distrib_vport_spec = vim.dvs.PortConnection(switchUuid=vdsuuid,
                                                        portgroupKey=pg_key)


            nic_spec = vim.host.VirtualNic.Specification(ip=ip_spec,
                                                         distributedVirtualPort=distrib_vport_spec)
            return nic_spec
        except Exception as e:
            self.module.fail_json(msg="ERROR building vmk spec--> %s" % str(e))

    def build_host_profilespec(self, hostprofilename, reference_host):
        hostprofile_spec = \
            vim.profile.host.HostProfile.HostBasedConfigSpec(name=hostprofilename,
                                                             enabled=True,
                                                             host=reference_host,
                                                             useHostProfileEngine=True)
        if hostprofile_spec:
            return False, hostprofile_spec
        else:
            return True, None

#########################################################
##  select_ip is for DEMO ONLY
#########################################################

    def select_ip(self, net_cider):
        try:
            ips = IPNetwork(net_cider)
            network_addr = ips.network
            bcast = ips.broadcast
            netmask = ips.netmask

            ip_list = list(ips)
            for ip in ip_list:
                if ip == network_addr or ip == bcast:
                    ip_list.remove(ip)

            ip_choice = random.choice(ip_list)
            return str(ip_choice), str(netmask)
        except Exception as e:
            self.module.fail_json(msg=e)

#########################################################
##  select_ip is for DEMO ONLY
#########################################################

    def configure_host(self, host, datacenter):

        vim_host = self.get_target_object([vim.HostSystem], host)

        if vim_host:
            compatible = self.host_compatibility(vim_host, self.vds(), datacenter)
            configured, anymissing = self.check_host_proxyswitch(vim_host)
        else:
            return True, dict(msg="Failed to locate host")

        if not configured and anymissing is None:

            if compatible:
                failed, task_msg = self.reconfigure_vds_task(self.vds(), vim_host)

                if not failed:
                    failed, host_netconfig = \
                        self.build_host_netconfig(host, self.vdsuuid(), self.uplink_key(), self.management_port_key())

                    if not failed:
                        net_system = vim_host.configManager.networkSystem
                        net_system.UpdateNetworkConfig(host_netconfig, "modify")

                        vmk_types = ['vmotion', 'storage']

                        for vmk_type in vmk_types:
                            self.add_vmk(vim_host, vmk_type, None)

                        configured, anymissing = self.check_host_proxyswitch(vim_host)

                        if configured:
                            return False, dict(msg="configured host")
                        else:
                            return True, dict(msg="failed to configure host")
            else:
                return True, dict(msg="Host %s is not compatible with VDS" % host)

        elif not configured and anymissing:

            for missing_vmk in anymissing:
                self.add_missing_vmk(vim_host, missing_vmk)

            configured, anymissing = self.check_host_proxyswitch(vim_host)

            if configured:
                return False, dict(msg="Host %s configured: %s" % (host, configured))
        else:
            message = "Host %s already configured" % host
            return False, dict(msg=message)

    def remove_vswitch(self, host):
        try:
            vim_host = self.get_target_object([vim.HostSystem], host)

            net_manager = vim_host.configManager.networkSystem

            net_info = net_manager.networkInfo

            check = net_info.vswitch

            if check:
                target_vswitch = net_manager.networkInfo.vswitch[0].name
                net_manager.RemoveVirtualSwitch(target_vswitch)

                return False, "Removed vSwitch: %s" % target_vswitch
            else:
                return False, "vSwitch not present no need to remove"

        except Exception as e:
            return True, "exception: %s" % e

def core(module):

    create_dc_clusters = module.params.get('create_dc_clusters')
    add_hosts_all = module.params.get('add_hosts')
    config_hosts = module.params.get('config_hosts')
    usehostname = module.params.get('usehostname')
    singlehost = module.params.get('singlehost')
    esxhost = module.params.get('esxhost')
    hostprofiles = module.params.get('hostprofiles')
    apply_hostprofiles = module.params.get('apply_hostprofiles')

    if create_dc_clusters:

        d = Datacenter(module)
        dc_status, dc_check = d.check_dc()

        if not dc_status:
            dc = d.create_datacenter()

            if isinstance(dc, vim.Datacenter):
                c = Cluster(module)
                clusters = c.create_clusters()

                message = "Created Datacenter: %s with Clusters: %s" % (dc.name, clusters)
                return False, message
        else:
            c = Cluster(module)
            status, need_to_add = c.cluster_check(dc_check)

            if status:
                clusters_added = c.create_clusters()
                return False, clusters_added
            else:
                message = "Datacenter: %s with Clusters: %s already present" \
                          % (c.datacenter_name, c.clusters_names)
                return False, message

    if add_hosts_all:

        h = Hosts(module)

        if singlehost == 'yes':

            failed, result = h.add_hosts_clusters(esxhost['name'], esxhost['cluster'])
            return failed, result

        else:
            failed, result = h.add_hosts_clusters()
            return failed, result

    if config_hosts or hostprofiles or apply_hostprofiles:

        conf = Hosts(module)

        host_state = {}

        if usehostname:
            if singlehost == 'yes':
                hosts = [esxhost['name']]
            else:
                hosts = [host for host in conf.clusters_dnsname.itervalues()]
        else:
            if singlehost == 'yes':
                hosts = [esxhost['name']]
            else:
                hosts = [host for host in conf.clusters_ips.itervalues()]

        dc = conf.get_target_object([vim.Datacenter], conf.datacenter_name)

        if isinstance(dc, vim.Datacenter):
            dc = dc
        else:
            conf.module.fail_json(msg="Could not get datacenter")

        if config_hosts:
            for host in hosts:

                status, msg = conf.configure_host(host, dc)

                if not status:
                    failed, message = conf.remove_vswitch(host)

                host_state.update({host: {}})
                host_state[host].update({'Configure host FAILED': status})
                host_state[host].update({'message': msg})
                host_state[host].update({'Removed vSwitch': message})

            return False, host_state

        if hostprofiles:
            for host in hosts:

                host_profile_status, message = conf.add_hostprofile_cluster(host)

                host_state.update({host: {}})

                host_state[host].update({'hostprofile FAILED': host_profile_status})

            return False, host_state

        if apply_hostprofiles:

            for host in hosts:

                vim_host = conf.get_target_object([vim.HostSystem], host)

                mode = conf.check_maintenance_mode(vim_host)

                if mode:

                    failed, msg = conf.apply_hostprofile(host)

                    if not failed:
                        exit_maintenance_mode = vim_host.ExitMaintenanceMode(0)

                        failed_maint, task_msg = conf.wait_for_task(exit_maintenance_mode)

                        host_state.update({host: {}})
                        host_state[host].update({'APPLIED PROFILE FAILED': failed})
                        host_state[host].update({'Apply Profile': msg})
                        host_state[host].update({'Maintenance Mode': task_msg })

                    else:
                        host_state.update({host: {}})
                        host_state[host].update({'APPLIED PROFILE FAILED': failed})

            return False, host_state

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            login=dict(required=True),
            password=dict(required=True),
            port=dict(type='int'),
            datacenter=dict(type='dict', required=True),
            esxhost=dict(type='dict', required=False),
            singlehost=dict(type='str', default='no'),
            create_dc_clusters=dict(required=True, choices=BOOLEANS),
            add_hosts=dict(required=True, choices=BOOLEANS),
            usehostname=dict(required=False, choices=BOOLEANS, default=False),
            config_hosts=dict(required=True, choices=BOOLEANS),
            hostprofiles=dict(required=True, choices=BOOLEANS),
            apply_hostprofiles=dict(required=True, choices=BOOLEANS)
        )
    )

    fail, result = core(module)

    if fail:
        module.fail_json(changed=False, msg=result)
    else:
        module.exit_json(changed=True, msg=result)

from ansible.module_utils.basic import *
main()
