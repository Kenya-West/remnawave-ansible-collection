#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: external_squads
short_description: Manage many Remnawave external squads
description:
- The batch counterpart of M(kenyawest.remnawave.external_squad). Each entry has the same semantics.
- All entries are planned before writing. Duplicate identifiers and invalid references fail
  without writes.
- Deletions go first, followed by updates and creations. Writes run up to parallelism at a time.
- With order disabled, creations run sequentially. Otherwise one reorder request establishes
  list order.
- A rejected write stops further steps. Completed entries are returned; already applied writes
  cannot be rolled back.
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
- kenyawest.remnawave.remnawave
options:
  parallelism:
    description: Maximum concurrent writes within each step.
    type: int
    default: 4
  order:
    description: Put listed entities in list order, leaving unlisted entities in their slots.
    type: bool
    default: true
  squads:
    description: Entities to manage, with the options of M(kenyawest.remnawave.external_squad).
      Unlisted entities are left alone.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description:
        - Name of the external squad.
        type: str
        required: true
      state:
        description:
        - Whether the squad should exist.
        type: str
        choices:
        - present
        - absent
        default: present
      tags:
        description:
        - Tags of the squad. Authoritative when set; an empty list removes every tag.
        - At most 10 tags, each up to 36 characters of uppercase letters, digits, underscores
          and colons.
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
        description: HWID settings in panel camelCase format, as a dict or JSON string. The
          JSON string C(null) clears the override.
        type: raw
      custom_remarks:
        description: Custom remarks in panel camelCase format, as a dict or JSON string. The
          JSON string C(null) clears the override.
        type: raw
      subpage_config_uuid:
        description: Subscription page configuration UUID. An empty string removes the override.
        type: str
attributes:
  check_mode:
    description: Predict changes without modifying the panel.
    support: full
  diff_mode:
    description: Report changed fields.
    support: full
'''

EXAMPLES = r'''
- name: Manage external squads
  kenyawest.remnawave.external_squads:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    squads:
      - name: retired-entity
        state: absent
'''

RETURN = r'''
results:
  description: Per-entry results in input order. On failure, entries completed in
    full.
  type: list
  elements: dict
  returned: always
  contains:
    name:
      description: Identifier as supplied.
      type: str
      returned: always
    action:
      description: create, update, delete or none.
      type: str
      returned: always
    changed:
      description: Whether the entity changed.
      type: bool
      returned: always
    squad:
      description: API entity or predicted entity in check mode.
      type: dict
      returned: when present
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.batch import DEFAULT_PARALLELISM
from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec
from ansible_collections.kenyawest.remnawave.plugins.module_utils.squad import (
    entity_options, run_batch,
)


def main():
    spec = remnawave_argument_spec()
    spec.update(parallelism=dict(type='int', default=DEFAULT_PARALLELISM),
                order=dict(type='bool', default=True),
                squads=dict(type='list', elements='dict', required=True,
                            options=entity_options('external_squad')))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params['parallelism'] < 1:
        module.fail_json(msg='parallelism must be at least 1')
    client = RemnawaveClient(module)
    try:
        run_batch(module, client, 'external_squad')
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
