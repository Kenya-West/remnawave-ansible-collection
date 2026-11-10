#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: subscription_templates
short_description: Manage many Remnawave subscription templates
description:
- The batch counterpart of M(kenyawest.remnawave.subscription_template). Each entry has the
  same semantics.
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
  templates:
    description: Entities to manage, with the options of M(kenyawest.remnawave.subscription_template).
      Unlisted entities are left alone.
    type: list
    elements: dict
    required: true
    suboptions:
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
        description: Authoritative JSON object, as a dict or JSON string. Mutually exclusive
          with template_yaml.
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
- name: Manage subscription templates
  kenyawest.remnawave.subscription_templates:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    templates:
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
    template:
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
                templates=dict(type='list', elements='dict', required=True,
                               options=entity_options('subscription_template')))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params['parallelism'] < 1:
        module.fail_json(msg='parallelism must be at least 1')
    client = RemnawaveClient(module)
    try:
        run_batch(module, client, 'subscription_template')
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
