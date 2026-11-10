#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: response_rule_info
short_description: Retrieve Remnawave rules
description:
- Read all entities or filter by name. Missing entities return an empty list.
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
- kenyawest.remnawave.remnawave
options:
  name:
    description: Optional rule name to find.
    type: str
attributes:
  check_mode:
    description: Predict changes without modifying the panel.
    support: full
'''

EXAMPLES = r'''
- name: Read rules
  kenyawest.remnawave.response_rule_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
'''

RETURN = r'''
rules:
  description: Matching entities in panel camelCase format.
  type: list
  elements: dict
  returned: always
settings:
  description: Response rule configuration settings.
  type: dict
  returned: always
version:
  description: Response rule configuration version.
  type: str
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec


def main():
    spec = remnawave_argument_spec()
    spec.update(name=dict(type='str'))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = RemnawaveClient(module)
    try:
        config = client.get('/api/subscription-settings').get('responseRules') or {}
        rules = config.get('rules', [])
        if module.params['name'] is not None:
            rules = [r for r in rules if r['name'] == module.params['name']]
        module.exit_json(changed=False, rules=rules, settings=config.get('settings', {}),
                         version=config.get('version', '1'))
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
