#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: response_rules
short_description: Manage Remnawave subscription response rules
description:
- Manage named rules within the subscription-settings singleton, preserving unlisted rules and
  configuration settings.
- Only supplied fields are patched. Conditions and response modifications are authoritative
  when set.
- Rules are evaluated in order, first match wins. New rules append; use response_rules to manage
  order.
- All entries are validated before one PATCH replaces the rule configuration. Avoid concurrent
  writers to this singleton.
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
- kenyawest.remnawave.remnawave
options:
  rules:
    description: Rules to manage. Unlisted rules and configuration settings are preserved.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description: Unique rule name, 1 to 50 characters.
        type: str
        required: true
      state:
        description: Existence and enabled state. present preserves existing enabled state.
        type: str
        choices:
        - present
        - absent
        - enabled
        - disabled
        default: present
      description:
        description: Human-readable rule description.
        type: str
      operator:
        description: How conditions are combined. Defaults to AND on creation.
        type: str
        choices:
        - AND
        - OR
      conditions:
        description: Authoritative ordered conditions. Defaults to an empty list on creation.
        type: list
        elements: dict
        suboptions:
          header_name:
            description: HTTP request header name.
            type: str
            required: true
          operator:
            description: Header comparison operator.
            type: str
            required: true
            choices:
            - EQUALS
            - NOT_EQUALS
            - CONTAINS
            - NOT_CONTAINS
            - STARTS_WITH
            - NOT_STARTS_WITH
            - ENDS_WITH
            - NOT_ENDS_WITH
            - REGEX
            - NOT_REGEX
          value:
            description: Comparison value.
            type: str
            required: true
          case_sensitive:
            description: Whether comparison is case sensitive.
            type: bool
            default: false
      response_type:
        description: Response format or blocking action. Required on creation.
        type: str
        choices:
        - XRAY_JSON
        - XRAY_BASE64
        - MIHOMO
        - STASH
        - CLASH
        - SINGBOX
        - BROWSER
        - BLOCK
        - STATUS_CODE_404
        - STATUS_CODE_451
        - SOCKET_DROP
      response_modifications:
        description: Authoritative modifications in panel camelCase format, as a dict or JSON
          string. subscriptionTemplate references a template by name, as the panel expects.
        type: raw
  order:
    description: Arrange listed rules in input order among their existing slots.
    type: bool
    default: true
attributes:
  check_mode:
    description: Predict changes without modifying the panel.
    support: full
  diff_mode:
    description: Report changed fields.
    support: full
'''

EXAMPLES = r'''
- name: Block legacy clients
  kenyawest.remnawave.response_rules:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    rules:
      - name: block-legacy
        response_type: BLOCK
'''

RETURN = r'''
results:
  description: Per-rule results in input order.
  type: list
  elements: dict
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec
from ansible_collections.kenyawest.remnawave.plugins.module_utils.response_rule import (
    response_rule_options, run_response_rules,
)


def main():
    spec = remnawave_argument_spec()
    spec.update(rules=dict(type='list', elements='dict', required=True, options=response_rule_options()),
                order=dict(type='bool', default=True))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = RemnawaveClient(module)
    try:
        run_response_rules(module, client, batch=True)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc)


if __name__ == '__main__':
    main()
