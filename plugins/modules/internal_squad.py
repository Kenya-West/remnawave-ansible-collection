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
  - Inbounds are referenced by tag, optionally together with their config
    profile, or by UUID, and resolved automatically. The list is
    authoritative when set.
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
      - Each item is an inbound tag or UUID as a plain string, or a dict with
        C(tag) (inbound tag or UUID) and optionally C(profile) (config profile
        name or UUID), which the inbound must then belong to.
      - Inbound tags are unique across config profiles, so the plain tag is
        enough; the dict form is kept for playbooks written before plain tags
        were accepted.
      - Required when the squad does not exist yet.
    type: list
    elements: raw
  tags:
    description:
      - Tags of the squad. Authoritative when set; an empty list removes
        every tag.
      - At most 10 tags, each up to 36 characters of uppercase letters,
        digits, underscores and colons.
      - Not to be confused with the inbound C(tag) inside O(inbounds).
    type: list
    elements: str
    version_added: 1.2.0
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
      - vless-reality
      - ss-inbound
    tags:
      - PAID

- name: The same, naming the config profile of an inbound as well
  kenyawest.remnawave.internal_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: default-squad
    inbounds:
      - profile: default-profile
        tag: vless-reality
      - ss-inbound

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
    tags_differ, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_internal_squad, resolve_inbound_uuids, set_tags,
)


def resolve_inbounds(module, client, items):
    uuids = []
    for item in items:
        if isinstance(item, str) and is_uuid(item):
            uuids.append(item)
            continue
        if isinstance(item, str):
            profile, tag = None, item
        elif isinstance(item, dict) and 'tag' in item:
            profile, tag = item.get('profile'), item['tag']
        else:
            module.fail_json(
                msg='Each inbound must be an inbound tag or UUID, or a dict '
                    'with a tag key and optionally a profile key, got: %r'
                    % (item,))
        resolved = resolve_for_check_mode(
            module,
            lambda: resolve_inbound_uuids(client, profile, [tag])[1],
            [tag if profile is None else '%s:%s' % (profile, tag)])
        uuids.extend(resolved)
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

    tags = validate_tags(params['tags'])
    desired_uuids = None
    if params['inbounds'] is not None:
        desired_uuids = resolve_inbounds(module, client, params['inbounds'])

    if current is None:
        if desired_uuids is None:
            module.fail_json(
                msg='inbounds is required when creating internal squad %r' % name)
        payload = {'name': name, 'inbounds': desired_uuids}
        after = dict(payload)
        if tags:
            after['tags'] = tags
        if module.check_mode:
            exit_with_change(module, {}, after, squad=after)
        created = client.post('/api/internal-squads', payload)
        # Tags are not part of the create body; they have their own endpoint.
        if tags:
            created = set_tags(client, 'internal-squads', created, tags)
        exit_with_change(module, {}, after, squad=created)

    before, after = {}, {}
    current_uuids = sorted(i.get('uuid') for i in (current.get('inbounds') or []))
    inbounds_changed = (desired_uuids is not None
                        and sorted(set(desired_uuids)) != current_uuids)
    if inbounds_changed:
        before['inbounds'] = current_uuids
        after['inbounds'] = sorted(set(desired_uuids))
    tags_changed = tags_differ(tags, current.get('tags'))
    if tags_changed:
        before['tags'] = current.get('tags') or []
        after['tags'] = tags

    if not inbounds_changed and not tags_changed:
        module.exit_json(changed=False, squad=current)
    if module.check_mode:
        exit_with_change(module, before, after, squad=current)

    squad = current
    if inbounds_changed:
        squad = client.patch(
            '/api/internal-squads',
            {'uuid': current['uuid'], 'inbounds': desired_uuids})
    if tags_changed:
        squad = set_tags(client, 'internal-squads', squad or current, tags)
    exit_with_change(module, before, after, squad=squad)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        inbounds=dict(type='list', elements='raw'),
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
