#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: host_info
short_description: Retrieve Remnawave hosts
description:
  - Retrieve hosts of a Remnawave panel by remark or by address, or list all
    of them.
  - Looking hosts up by address is what turns a list of domains into the
    hosts serving them; unlike M(kenyawest.remnawave.host), this module does
    not mind an address that matches several hosts and returns all of them.
  - This module never changes anything and always returns C(changed=false).
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
  - kenyawest.remnawave.remnawave
attributes:
  check_mode:
    description:
      - Can run in C(check_mode) and predict changes without modifying the panel.
    support: full
  diff_mode:
    description:
      - Returns what changed (or would change) when run with C(--diff).
    support: none
options:
  remark:
    description:
      - Return only the host with this remark.
      - Mutually exclusive with O(address); when both are omitted, all hosts
        are returned.
    type: str
  address:
    description:
      - Return only the hosts whose address is this domain or IP.
      - Several hosts may share an address, so this may return more than one.
    type: str
seealso:
  - module: kenyawest.remnawave.host
'''

EXAMPLES = r'''
- name: List all hosts
  kenyawest.remnawave.host_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
  register: result

- name: Collect the hosts serving a list of domains
  kenyawest.remnawave.host_info:
    address: "{{ item }}"
  loop: "{{ retired_domains }}"
  register: matched

- name: Disable every one of them, whatever its remark
  kenyawest.remnawave.host:
    remark: "{{ item.remark }}"
    state: disabled
  loop: "{{ matched.results | map(attribute='hosts') | flatten }}"
  loop_control:
    label: "{{ item.remark }}"
'''

RETURN = r'''
hosts:
  description:
    - Matching hosts as returned by the Remnawave API (camelCase keys).
    - Always a list, empty when nothing matched.
  type: list
  elements: dict
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_hosts_by, list_hosts,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        remark=dict(type='str'),
        address=dict(type='str'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[('remark', 'address')],
    )

    client = RemnawaveClient(module)
    try:
        if module.params['remark']:
            hosts = find_hosts_by(client, module.params['remark'], key='remark')
        elif module.params['address']:
            hosts = find_hosts_by(client, module.params['address'], key='address')
        else:
            hosts = list_hosts(client)
        module.exit_json(changed=False, hosts=hosts)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
