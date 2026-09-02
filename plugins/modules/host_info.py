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
  - Retrieve one host by remark, or list all hosts of a Remnawave panel.
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
      - When omitted, all hosts are returned.
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
'''

RETURN = r'''
hosts:
  description: Matching hosts as returned by the Remnawave API (camelCase keys).
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
    find_host, list_hosts,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(remark=dict(type='str'))
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        if module.params['remark']:
            host = find_host(client, module.params['remark'])
            hosts = [host] if host is not None else []
        else:
            hosts = list_hosts(client)
        module.exit_json(changed=False, hosts=hosts)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
