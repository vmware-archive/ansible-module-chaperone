ansible-module-supervio
========================

[Ansible](https://github.com/ansible/ansible) module for manipulating
bits and pieces of vSphere, vCenter, NSX and other portions of VIO
related technologies.

# Minimal Requirements

* Python ``urllib2``
* Python ``ast``
* Python ``datetime``
* VMware 'pyVmomi"

# Notes

None yet.

# Examples:
### Create a new virtual distributed switch
- name: Create VDS
  local_action:
    module: vds
    hostname: myvCenter.corp.local
    vs_port: 443
    username: "admin@vsphere.local"
    password: "some_sneaky_password"
    vds_name: "myVIOVDS"
    numUplinks: 8
    numPorts: 128
    networkIOControl: true
    productVersion: "6.0.0"
    state: present

# License
TBD
