#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: internal_squads
short_description: Manage many Remnawave internal squads
description:
- The batch counterpart of M(kenyawest.remnawave.internal_squad). Each entry has the same semantics.
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
    description: Entities to manage, with the options of M(kenyawest.remnawave.internal_squad).
      Unlisted entities are left alone.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description:
        - Name of the internal squad. This is the stable identifier the module searches by;
          it cannot be changed through this module.
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
      inbounds:
        description:
        - Inbounds that belong to the squad.
        - Each item is an inbound tag or UUID as a plain string, or a dict with C(tag) (inbound
          tag or UUID) and optionally C(profile) (config profile name or UUID), which the inbound
          must then belong to.
        - Inbound tags are unique across config profiles, so the plain tag is enough; the dict
          form is kept for playbooks written before plain tags were accepted.
        - Required when the squad does not exist yet.
        type: list
        elements: raw
      tags:
        description:
        - Tags of the squad. Authoritative when set; an empty list removes every tag.
        - At most 10 tags, each up to 36 characters of uppercase letters, digits, underscores
          and colons.
        - Not to be confused with the inbound C(tag) inside O(squads[].inbounds).
        type: list
        elements: str
        version_added: 1.2.0
attributes:
  check_mode:
    description: Predict changes without modifying the panel.
    support: full
  diff_mode:
    description: Report changed fields.
    support: full
'''

EXAMPLES = r'''
- name: Manage internal squads
  kenyawest.remnawave.internal_squads:
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

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import remnawave_argument_spec
from ansible_collections.kenyawest.remnawave.plugins.module_utils.squad import (
    DEFAULT_PARALLELISM, entity_options, run_batch,
)


def main():
    spec = remnawave_argument_spec()
    spec.update(parallelism=dict(type='int', default=DEFAULT_PARALLELISM),
                order=dict(type='bool', default=True),
                squads=dict(type='list', elements='dict', required=True,
                            options=entity_options('internal_squad')))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params['parallelism'] < 1:
        module.fail_json(msg='parallelism must be at least 1')
    client = RemnawaveClient(module)
    try:
        run_batch(module, client, 'internal_squad')
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
