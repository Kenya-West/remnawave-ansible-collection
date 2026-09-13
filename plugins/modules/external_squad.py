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
  - Create and delete external squads of a Remnawave panel, and manage
    their tags.
  - Squads are identified by their C(name). Users are assigned to an external
    squad through M(kenyawest.remnawave.user).
  - Advanced per-squad settings (templates, host overrides, response headers
    and so on) are not modeled by this module; use
    M(kenyawest.remnawave.api) for those.
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
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    exit_with_change, remnawave_argument_spec, tags_differ, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_external_squad, set_tags,
)


def run(module, client):
    params = module.params
    name = params['name']
    current = find_external_squad(client, name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.delete('/api/external-squads/%s' % current['uuid'])
        exit_with_change(module, {'name': name}, {})

    tags = validate_tags(params['tags'])

    if current is None:
        payload = {'name': name}
        after = dict(payload)
        if tags:
            after['tags'] = tags
        if module.check_mode:
            exit_with_change(module, {}, after, squad=after)
        created = client.post('/api/external-squads', payload)
        # Tags are not part of the create body; they have their own endpoint.
        if tags:
            created = set_tags(client, 'external-squads', created, tags)
        exit_with_change(module, {}, after, squad=created)

    if not tags_differ(tags, current.get('tags')):
        module.exit_json(changed=False, squad=current)

    before = {'tags': current.get('tags') or []}
    after = {'tags': tags}
    if module.check_mode:
        exit_with_change(module, before, after, squad=current)
    updated = set_tags(client, 'external-squads', current, tags)
    exit_with_change(module, before, after, squad=updated)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        tags=dict(type='list', elements='str'),
    )
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
