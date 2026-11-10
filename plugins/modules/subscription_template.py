#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: subscription_template
short_description: Manage Remnawave subscription templates
description:
- Create, update and delete subscription templates by name or UUID.
- Only supplied options are managed. Content and tags are authoritative when set.
- The API creates a default template first; content and tags are applied afterwards.
- The template listing omits content. Existing templates are read individually for comparison.
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
- kenyawest.remnawave.remnawave
options:
  name:
    description: Template name or UUID. New names must be 2 to 255 characters.
    type: str
    required: true
  state:
    description: Whether the template should exist.
    type: str
    choices:
    - present
    - absent
    default: present
  template_type:
    description: Template type. Required on creation; immutable afterwards.
    type: str
    choices:
    - XRAY_JSON
    - XRAY_BASE64
    - MIHOMO
    - STASH
    - CLASH
    - SINGBOX
  template_json:
    description: Authoritative JSON object, as a dict or JSON string. Mutually exclusive with
      template_yaml.
    type: raw
  template_yaml:
    description: Authoritative plain-text YAML content, encoded to base64 for the API. Mutually
      exclusive with template_json.
    type: str
  tags:
    description: Authoritative tags. Up to 10 uppercase tags; an empty list clears them.
    type: list
    elements: str
attributes:
  check_mode:
    description: Predict changes without modifying the panel.
    support: full
  diff_mode:
    description: Report changed fields.
    support: full
'''

EXAMPLES = r'''
- name: Declare a custom template
  kenyawest.remnawave.subscription_template:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: custom-mihomo
    template_type: MIHOMO
    template_yaml: "{{ lookup('file', 'mihomo.yml') }}"
'''

RETURN = r'''
template:
  description: Subscription template as returned by the API.
  type: dict
  returned: when present
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec
from ansible_collections.kenyawest.remnawave.plugins.module_utils.squad import entity_options, run_single


def main():
    spec = remnawave_argument_spec()
    spec.update(entity_options('subscription_template'))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    client = RemnawaveClient(module)
    try:
        run_single(module, client, 'subscription_template')
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
