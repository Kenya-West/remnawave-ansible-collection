#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: subscription_settings
short_description: Manage Remnawave subscription settings
description:
  - Update the panel-wide subscription settings of a Remnawave panel.
  - This is a singleton resource; it always exists and cannot be deleted.
    Only the options you set are managed.
  - Structured options (O(custom_remarks), O(response_rules),
    O(hwid_settings)) are compared by deep equality and are authoritative
    when set.
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
    support: full
options:
  serve_json_at_base_subscription:
    description:
      - Whether to serve JSON at the base subscription URL.
    type: bool
  show_custom_remarks:
    description:
      - Whether custom remarks are shown to clients.
    type: bool
  custom_remarks:
    description:
      - Custom remarks structure, as a dict or JSON string. See the panel
        documentation for the expected shape.
    type: raw
  custom_response_headers:
    description:
      - Extra HTTP headers returned with subscription responses.
    type: dict
  randomize_hosts:
    description:
      - Whether hosts are served in randomized order.
    type: bool
  response_rules:
    description:
      - Subscription response rules structure, as a dict or JSON string.
    type: raw
  hwid_settings:
    description:
      - HWID device settings structure, as a dict or JSON string.
    type: raw
seealso:
  - module: kenyawest.remnawave.system_info
'''

EXAMPLES = r'''
- name: Configure subscription behaviour
  kenyawest.remnawave.subscription_settings:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    serve_json_at_base_subscription: false
    randomize_hosts: true
'''

RETURN = r'''
settings:
  description: The subscription settings as returned by the Remnawave API.
  type: dict
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    FieldSpec, build_patch, exit_with_change, parse_json_option,
    remnawave_argument_spec,
)

FIELDS = [
    FieldSpec('serve_json_at_base_subscription', 'serveJsonAtBaseSubscription'),
    FieldSpec('show_custom_remarks', 'isShowCustomRemarks'),
    FieldSpec('custom_remarks', 'customRemarks', kind='json'),
    FieldSpec('custom_response_headers', 'customResponseHeaders', kind='json'),
    FieldSpec('randomize_hosts', 'randomizeHosts'),
    FieldSpec('response_rules', 'responseRules', kind='json'),
    FieldSpec('hwid_settings', 'hwidSettings', kind='json'),
]


def run(module, client):
    current = client.get('/api/subscription-settings')

    resolved = dict(module.params)
    for option in ('custom_remarks', 'response_rules', 'hwid_settings'):
        resolved[option] = parse_json_option(resolved[option], option, module)

    patch, before, after = build_patch(resolved, current, FIELDS)
    if not patch:
        module.exit_json(changed=False, settings=current)

    payload = dict(patch)
    payload['uuid'] = current['uuid']
    if module.check_mode:
        exit_with_change(module, before, after, settings=current)
    updated = client.patch('/api/subscription-settings', payload)
    exit_with_change(module, before, after, settings=updated)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        serve_json_at_base_subscription=dict(type='bool'),
        show_custom_remarks=dict(type='bool'),
        custom_remarks=dict(type='raw'),
        custom_response_headers=dict(type='dict'),
        randomize_hosts=dict(type='bool'),
        response_rules=dict(type='raw'),
        hwid_settings=dict(type='raw'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
