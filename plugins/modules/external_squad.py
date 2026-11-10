#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: external_squad
short_description: Manage Remnawave external squads
description:
  - Create, update and delete external squads and their subscription overrides.
  - Squads are identified by name or UUID. Users are assigned through
    M(kenyawest.remnawave.user).
  - Only supplied options are managed. Lists are authoritative; the nested
    subscription settings and host overrides preserve omitted suboptions.
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
  name:
    description:
      - Name of the external squad.
    type: str
    required: true
  state:
    description:
      - Whether the squad should exist.
    type: str
    choices: [present, absent]
    default: present
  tags:
    description:
      - Tags of the squad. Authoritative when set; an empty list removes
        every tag.
      - At most 10 tags, each up to 36 characters of uppercase letters,
        digits, underscores and colons.
    type: list
    elements: str
    version_added: 1.2.0
  templates:
    description:
      - Subscription template names or UUIDs, at most one per template type.
      - Authoritative when set; an empty list restores default templates.
    type: list
    elements: str
  subscription_settings:
    description: Per-squad subscription settings; omitted suboptions are preserved.
    type: dict
    suboptions:
      serve_json_at_base_subscription:
        description: Serve JSON at the base subscription URL.
        type: bool
      show_custom_remarks:
        description: Show custom remarks.
        type: bool
      randomize_hosts:
        description: Randomize host order.
        type: bool
  host_overrides:
    description: Per-squad host overrides; omitted suboptions are preserved.
    type: dict
    suboptions:
      server_description:
        description: Server description, up to 30 characters; an empty string clears it.
        type: str
      vless_route_id:
        description: VLESS route identifier as an integer; an empty string clears it.
        type: raw
  response_headers_add:
    description: Additional response headers; authoritative when set.
    type: dict
  response_headers_remove:
    description: Response header names to remove; authoritative when set.
    type: list
    elements: str
  hwid_settings:
    description: HWID settings in panel camelCase format, as a dict or JSON string. The JSON string C(null) clears the override.
    type: raw
  custom_remarks:
    description: Custom remarks in panel camelCase format, as a dict or JSON string. The JSON string C(null) clears the override.
    type: raw
  subpage_config_uuid:
    description: Subscription page configuration UUID. An empty string removes the override.
    type: str
seealso:
  - module: kenyawest.remnawave.external_squad_info
  - module: kenyawest.remnawave.user
'''

EXAMPLES = r'''
- name: Ensure external squad exists
  kenyawest.remnawave.external_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: resellers
    state: present
    tags:
      - PARTNER
'''

RETURN = r'''
squad:
  description: The external squad as returned by the Remnawave API.
  type: dict
  returned: when state=present
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec
from ansible_collections.kenyawest.remnawave.plugins.module_utils.squad import (
    entity_options, run_single,
)


def run(module, client):
    run_single(module, client, 'external_squad')


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(entity_options('external_squad'))
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
