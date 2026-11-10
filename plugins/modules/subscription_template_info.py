#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: subscription_template_info
short_description: Retrieve Remnawave templates
description:
- Read all entities or filter by name. Missing entities return an empty list.
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
- kenyawest.remnawave.remnawave
options:
  name:
    description: Optional name or UUID to find.
    type: str
attributes:
  check_mode:
    description: Predict changes without modifying the panel.
    support: full
'''

EXAMPLES = r'''
- name: Read templates
  kenyawest.remnawave.subscription_template_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
'''

RETURN = r'''
templates:
  description: Matching entities in panel camelCase format.
  type: list
  elements: dict
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_subscription_template, list_subscription_templates,
)


def main():
    spec = remnawave_argument_spec()
    spec.update(name=dict(type='str'))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = RemnawaveClient(module)
    try:
        templates = list_subscription_templates(client)
        if module.params['name'] is not None:
            template = find_subscription_template(client, module.params['name'])
            templates = [template] if template else []
        templates = [client.get('/api/subscription-templates/%s' % t['uuid'], cached=True)
                     for t in templates]
        module.exit_json(changed=False, templates=templates)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
