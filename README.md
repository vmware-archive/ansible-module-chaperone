ansible-module-chaperone
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

# License and Copyright
Copyright 2015 VMware, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

# Notices
See the [NOTICES](NOTICES) file for third party licenses incorporated herein.

## Author Information
This role was created in 2015 by [Tom Hite / VMware](http://www.vmware.com/).
