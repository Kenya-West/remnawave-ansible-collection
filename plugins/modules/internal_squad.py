#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: internal_squad
short_description: Manage Remnawave internal squads
description:
  - Create, update and delete internal squads of a Remnawave panel in a
    declarative way.
  - Squads are identified by their C(name).
  - Inbounds are referenced as C(profile-name:inbound-tag) pairs or plain
    inbound UUIDs and resolved automatically. The list is authoritative when
    set.
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
      - Name of the internal squad. This is the stable identifier the module
        searches by; it cannot be changed through this module.
    type: str
    required: true
  state:
    description:
      - Whether the squad should exist.
    type: str
    choices: [present, absent]
    default: present
  inbounds:
    description:
      - Inbounds that belong to the squad.
      - Each item is either a dict with C(profile) (config profile name or
        UUID) and C(tag) (inbound tag or UUID), or a plain inbound UUID
        string.
      - Required when the squad does not exist yet.
    type: list
    elements: raw
seealso:
  - module: kenyawest.remnawave.internal_squad_info
  - module: kenyawest.remnawave.user
'''

EXAMPLES = r'''
- name: Ensure internal squad exists
  kenyawest.remnawave.internal_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: default-squad
    state: present
    inbounds:
      - profile: default-profile
        tag: vless-reality

- name: Remove a squad
  kenyawest.remnawave.internal_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: old-squad
    state: absent
'''

RETURN = r'''
squad:
  description: The internal squad as returned by the Remnawave API.
  type: dict
  returned: when state=present
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    exit_with_change, is_uuid, remnawave_argument_spec, resolve_for_check_mode,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_internal_squad, resolve_inbound_uuids,
)


def resolve_inbounds(module, client, items):
    uuids = []
    for item in items:
        if isinstance(item, str) and is_uuid(item):
            uuids.append(item)
        elif isinstance(item, dict) and 'profile' in item and 'tag' in item:
            resolved = resolve_for_check_mode(
                module,
                lambda: resolve_inbound_uuids(
                    client, item['profile'], [item['tag']])[1],
                ['%s:%s' % (item['profile'], item['tag'])])
            uuids.extend(resolved)
        else:
            module.fail_json(
                msg='Each inbound must be an inbound UUID or a dict with '
                    'profile and tag keys, got: %r' % (item,))
    return uuids


def run(module, client):
    params = module.params
    name = params['name']
    current = find_internal_squad(client, name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.delete('/api/internal-squads/%s' % current['uuid'])
        exit_with_change(module, {'name': name}, {})

    desired_uuids = None
    if params['inbounds'] is not None:
        desired_uuids = resolve_inbounds(module, client, params['inbounds'])

    if current is None:
        if desired_uuids is None:
            module.fail_json(
                msg='inbounds is required when creating internal squad %r' % name)
        payload = {'name': name, 'inbounds': desired_uuids}
        if module.check_mode:
            exit_with_change(module, {}, payload, squad=payload)
        created = client.post('/api/internal-squads', payload)
        exit_with_change(module, {}, payload, squad=created)

    current_uuids = sorted(i.get('uuid') for i in (current.get('inbounds') or []))
    if desired_uuids is None or sorted(set(desired_uuids)) == current_uuids:
        module.exit_json(changed=False, squad=current)

    before = {'inbounds': current_uuids}
    after = {'inbounds': sorted(set(desired_uuids))}
    if module.check_mode:
        exit_with_change(module, before, after, squad=current)
    updated = client.patch(
        '/api/internal-squads',
        {'uuid': current['uuid'], 'inbounds': desired_uuids})
    exit_with_change(module, before, after, squad=updated)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        inbounds=dict(type='list', elements='raw'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
