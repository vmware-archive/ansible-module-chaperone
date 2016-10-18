#!/usr/bin/env python
#
#  Copyright 2015 VMware, Inc.
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

DOCUMENTATION = '''
module: vcenter_vro_config
Short_description: Runs specified workflow on vRO appliance
description:
    Module will run specified named workflow. Module specifically developed for the configuration
    of vRO appliance using some of the built in workflows designed to configure the appliance.
requirements:
    - pyvmomi 6
    - ansible 2.x
Tested on:
    - vcenter 6.0
    - pyvmomi 6
    - esx 6
    - ansible 2.1.2
    - VMware-vCO-Appliance-6.0.3.0-3000579_OVF10.ova
options:
    vro_server:
        description:
            - ip or hostname of the appliacne
        required: True
    vro_username:
        description:
            - username to auth against api
        required: True
    vro_password:
        description:
            - password for specified user
        required: True
    vro_workflow:
        description:
            - Named workflow to run
        required: True
    vro_post_data:
        description:
            - json file used for the rest call to run the workflow
        required: True
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True
'''

EXAMPLE = '''
create a json file for the rest call

- name: VIO Rest Host Template
  template:
    src: "{{ rest_host_template_src }}"
    dest: "{{ rest_host_templtes_dest }}"
  with_items:
    - { rest_host_name: "{{ vio_rest_host_name }}", rest_host_url: "{{ vio_rest_host_url }}" }
  tags:
    - vro_config_templates

use the json file just created as inputfor module

- name: vro config Add VIO rest host
  vcenter_vro_config:
    vro_server: "{{ vro_ip }}"
    vro_username: 'vcoadmin'
    vro_password: 'vcoadmin'
    vro_workflow: "Add a REST host"
    vro_post_data: "{{ item }}"
    state: 'present'
  with_items:
    - "{{ rest_host_templtes_dest }}"
  tags:
    - vro_config_resthost
'''


try:
    import time
    import requests
    import json
    import uuid
    import logging
    from urlparse import urlparse
    IMPORTS = True
except ImportError:
    IMPORTS = False

LOG = logging.getLogger(__name__)
handler = logging.FileHandler('/tmp/vro_config.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
LOG.addHandler(handler)
LOG.setLevel(logging.DEBUG)


class VROClient(object):
    """
    vRO config
    """

    BASE_URL = "https://{}:8281/vco/{}"

    def __init__(self, module, verify=False):
        self.module = module
        self.user = self.module.params['vro_username']
        self.pwd = self.module.params['vro_password']
        self.server = self.module.params['vro_server']
        self.verify = verify
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        self.auth = requests.auth.HTTPBasicAuth(self.user, self.pwd)


    def _api_url(self, path):
        api_url_template = "api/{}"
        api_path = api_url_template.format(path)
        return self.BASE_URL.format(self.server, api_path)


    def _fail(self, msg):
        fail_msg = "Message: {}".format(msg)
        LOG.error(msg)
        self.module.fail_json(msg=fail_msg)


    def json_to_data(self, json_file):

        with open(json_file) as fb:
            json_data = json.load(fb)

        return json_data


    def _do_get(self, path):

        url = self._api_url(path)
        req_id = uuid.uuid4()
        LOG.info("ID: {} Request GET: {}".format(req_id, url))

        resp = None

        try:
            resp = requests.get(url=url, verify=self.verify,
                                auth=self.auth, headers=self.headers)
        except requests.exceptions.ConnectionError as e:
            self._fail('ID: {} Requests ConnectionError: {}'.format(req_id, e.message))

        return resp


    def _do_post(self, path, data):

        url = self._api_url(path)
        req_id = uuid.uuid4()
        LOG.debug("ID: {} Request POST: {}".format(req_id, url))

        resp = None

        try:
            resp = requests.post(url=url, json=data, verify=self.verify,
                                 headers=self.headers, auth=self.auth)
        except requests.exceptions.ConnectionError, c:
            self._fail("Requests ConnectionError: {}".format(c.message))

        LOG.debug("Request ID: {} POST: {} STATUS CODE: {}".format(req_id, url, resp.status_code))

        return resp


    def workflow_id(self, wf_name):

        path = 'workflows?conditions=name={}'.format(wf_name)
        wf_href = None

        resp = self._do_get(path)

        content = json.loads(resp.content)

        if content['total'] != 1:
            self._fail("Could not find workflow: {}".format(wf_name))

        for i in content['link']:
            wf_href = [x['value'] for x in i['attributes'] if x['name'] == 'id'][0]

        return wf_href


    def run_workflow(self, workflow_name, json_data):

        workflow_id = self.workflow_id(workflow_name)
        path = "workflows/{}/executions/".format(workflow_id)
        data = self.json_to_data(json_data)

        wf_post = self._do_post(path, data)

        if wf_post.status_code != 202:
            fail_msg = "POST failed with status code: {}".format(wf_post.status_code)
            self._fail(fail_msg)

        header = wf_post.headers
        url = header['location']
        execution_id = urlparse(url).path.split('/')[-2]

        return execution_id


    def run_workflow_state(self, workflow_name, execution_id):

        workflow_id = self.workflow_id(workflow_name)
        path = "workflows/{}/executions/{}/state".format(workflow_id, execution_id)

        get_state = self._do_get(path)

        if get_state.status_code != 200:
            fail_msg = "Failed to get state workflow: {} execution id: {}".format(workflow_name, execution_id)
            self._fail(fail_msg)

        content = json.loads(get_state.content)

        return content['value']


    def wait_for_workflow(self, workflow_name, execution_id, sleep_time=5):
        status_poll_count = 0

        while status_poll_count < 30:

            workflow_state = self.run_workflow_state(workflow_name, execution_id)

            if workflow_state == 'failed':
                return False

            elif workflow_state == 'completed':
                return True

            else:
                status_poll_count += 1
                time.sleep(sleep_time)

            if status_poll_count == 30:
                return False


    def get_wf_run_status(self, workflow_name):

        workflow_id = self.workflow_id(workflow_name)
        path = "workflows/{}/executions/".format(workflow_id)

        wf_runs = self._do_get(path)

        if wf_runs.status_code != 200:
            self._fail("Failed getting runs for workflow: {} id: {}".format(workflow_name, workflow_id))

        content = json.loads(wf_runs.content)
        total = content['relations']['total']

        if not (total >= 1):
            self._fail("No runs found for {} id: {} total: {}".format(workflow_name, workflow_id, total))

        wfruns = [i[x] for i in content['relations']['link'] for x in i.iterkeys() if x == 'attributes']

        failed_wfs = []

        for wfrun in wfruns:
            wfdata = {}
            for i in wfrun:
                for key in i.iterkeys():
                    if i[key] in ('state', 'id', 'endDate'):
                        wfdata.update({i[key]: i['value']})

            if wfdata['state'] == 'failed':
                failed_wfs.append(wfdata['id'])

        return failed_wfs


def main():
    argument_spec = dict(
        vro_server=dict(required=True, type='str'),
        vro_username=dict(required=True, type='str'),
        vro_password=dict(required=True, type='str', no_log=True),
        vro_workflow=dict(required=True, type='str'),
        vro_post_data=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not IMPORTS:
        module.fail_json(msg='python modules failed to import required for this module')

    v = VROClient(module)

    workflow_name = module.params['vro_workflow']

    execution_id = v.run_workflow(workflow_name, module.params['vro_post_data'])

    if v.wait_for_workflow(workflow_name, execution_id):
        module.exit_json(changed=True, result=execution_id)

    module.fail_json(msg="Failed to execute workflow")


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()