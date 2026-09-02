#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: user
short_description: Manage Remnawave panel users
description:
  - Create, update, enable, disable and delete users of a Remnawave panel in
    a declarative way.
  - Users are identified by their C(username); UUIDs never need to appear in
    playbooks. Only the options you set are managed - omitted options are
    left untouched on the panel (PATCH semantics).
  - Squads are referenced by name and resolved to UUIDs automatically.
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
  username:
    description:
      - Username of the user. This is the stable identifier the module
        searches by; it cannot be changed through this module.
    type: str
    required: true
  state:
    description:
      - V(present) ensures the user exists and leaves the enabled/disabled
        status alone, so a user disabled in the panel stays disabled.
      - V(enabled) and V(disabled) additionally ensure that status, creating
        the user first if needed.
      - The panel derives the states C(LIMITED) (over traffic quota) and
        C(EXPIRED) itself for users that are not administratively disabled.
        V(enabled) treats those as already satisfied and leaves them alone,
        because forcing them back to C(ACTIVE) would only be undone by the
        panel on its next pass.
      - V(absent) deletes the user.
    type: str
    choices: [present, absent, enabled, disabled]
    default: present
  expire_at:
    description:
      - Expiration timestamp in ISO 8601 format, for example
        V(2027-01-01T00:00:00Z).
      - Required when the user does not exist yet.
    type: str
  traffic_limit:
    description:
      - Traffic limit as a byte count or a human-readable size such as
        V(100GB) or V(1.5TB). Suffix multiples are binary (1G = 1024^3),
        matching C(ansible.builtin.human_to_bytes).
      - V(0) means unlimited.
    type: raw
  traffic_limit_strategy:
    description:
      - When the panel resets the user's traffic counter.
    type: str
    choices: [no_reset, day, week, month, month_rolling]
  description:
    description:
      - Free-form description. Set to an empty string to clear it.
    type: str
  tag:
    description:
      - User tag. Set to an empty string to clear it.
    type: str
  email:
    description:
      - E-mail address. Set to an empty string to clear it.
    type: str
  telegram_id:
    description:
      - Telegram numeric ID.
    type: int
  hwid_device_limit:
    description:
      - Maximum number of hardware devices allowed for the user.
    type: int
  internal_squads:
    description:
      - Internal squads the user must belong to, by name or UUID.
      - When set, this is authoritative - the user's squad membership is made
        exactly this list.
    type: list
    elements: str
  external_squad:
    description:
      - External squad the user must belong to, by name or UUID.
      - Set to an empty string to remove the user from any external squad.
    type: str
seealso:
  - module: kenyawest.remnawave.user_info
  - module: kenyawest.remnawave.internal_squad
'''

EXAMPLES = r'''
- name: Ensure user exists
  kenyawest.remnawave.user:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    username: alice
    state: present
    expire_at: "2027-01-01T00:00:00Z"
    traffic_limit: 100GB
    traffic_limit_strategy: month
    internal_squads:
      - default-squad

- name: Disable a user without touching anything else
  kenyawest.remnawave.user:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    username: alice
    state: disabled

- name: Remove a user
  kenyawest.remnawave.user:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    username: old-user
    state: absent
'''

RETURN = r'''
user:
  description:
    - The user object as returned by the Remnawave API (camelCase keys).
    - Contains connection credentials (for example C(trojanPassword)); treat
      registered results accordingly.
  type: dict
  returned: when state is not absent
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    STATE_CHOICES, FieldSpec, build_patch, desired_enabled, exit_with_change,
    parse_traffic_limit, remnawave_argument_spec, resolve_for_check_mode,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_external_squad, get_user_by_username, resolve_internal_squad_uuids,
    user_action,
)

# The panel derives LIMITED/EXPIRED itself for users that are not
# administratively disabled, so only DISABLED counts as "not enabled".
DISABLED_STATUS = 'DISABLED'


def build_fields(module, client):
    params = module.params

    squad_uuids = None
    if params['internal_squads'] is not None:
        squad_uuids = resolve_for_check_mode(
            module,
            lambda: resolve_internal_squad_uuids(client, params['internal_squads']),
            params['internal_squads'])

    external_uuid_sentinel = params['external_squad']
    external_uuid = None
    if external_uuid_sentinel:
        external_uuid = resolve_for_check_mode(
            module,
            lambda: find_external_squad(
                client, external_uuid_sentinel, required=True)['uuid'],
            external_uuid_sentinel)

    fields = [
        FieldSpec('expire_at', 'expireAt', kind='time'),
        FieldSpec('traffic_limit', 'trafficLimitBytes',
                  to_api=parse_traffic_limit),
        FieldSpec('traffic_limit_strategy', 'trafficLimitStrategy',
                  to_api=lambda v: v.upper()),
        FieldSpec('description', 'description', to_api=lambda v: v or None),
        FieldSpec('tag', 'tag', to_api=lambda v: v or None),
        FieldSpec('email', 'email', to_api=lambda v: v or None),
        FieldSpec('telegram_id', 'telegramId'),
        FieldSpec('hwid_device_limit', 'hwidDeviceLimit'),
    ]
    resolved = dict(params)
    if squad_uuids is not None:
        fields.append(FieldSpec(
            'internal_squads', 'activeInternalSquads', kind='set',
            from_api=lambda v: [s.get('uuid') for s in (v or [])]))
        resolved['internal_squads'] = squad_uuids
    if external_uuid_sentinel is not None:
        fields.append(FieldSpec(
            'external_squad', 'externalSquadUuid',
            to_api=lambda dummy: external_uuid))
    return fields, resolved


def apply_enabled(module, client, current, wanted):
    """Reconcile the enable/disable action; returns True when it changed."""
    if wanted is None or current is None:
        return False
    currently_enabled = current.get('status') != DISABLED_STATUS
    if currently_enabled == wanted:
        return False
    if not module.check_mode:
        user_action(client, current['id'], 'enable' if wanted else 'disable')
    return True


def run(module, client):
    params = module.params
    username = params['username']
    state = params['state']
    current = get_user_by_username(client, username)

    if state == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.delete('/api/users/%s' % current['id'])
        exit_with_change(module, {'username': username}, {})

    wanted_enabled = desired_enabled(state)
    fields, resolved = build_fields(module, client)
    patch, before, after = build_patch(resolved, current, fields)

    if current is None:
        if params['expire_at'] is None:
            module.fail_json(
                msg='expire_at is required when creating user %r' % username)
        payload = dict(patch)
        payload['username'] = username
        after['username'] = username
        if wanted_enabled is False:
            # Users can be created disabled outright, no extra action needed.
            payload['status'] = DISABLED_STATUS
            after['status'] = DISABLED_STATUS
        if module.check_mode:
            exit_with_change(module, {}, after, user=payload)
        created = client.post('/api/users', payload)
        exit_with_change(module, {}, after, user=created)

    enabled_changed = apply_enabled(module, client, current, wanted_enabled)
    if enabled_changed:
        before['status'] = current.get('status')
        after['status'] = 'ACTIVE' if wanted_enabled else DISABLED_STATUS

    if patch:
        payload = dict(patch)
        payload['id'] = current['id']
        if not module.check_mode:
            client.patch('/api/users', payload)

    if not patch and not enabled_changed:
        module.exit_json(changed=False, user=current)

    user = current if module.check_mode else get_user_by_username(client, username)
    exit_with_change(module, before, after, user=user)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        username=dict(type='str', required=True),
        state=dict(type='str', choices=STATE_CHOICES, default='present'),
        expire_at=dict(type='str'),
        traffic_limit=dict(type='raw'),
        traffic_limit_strategy=dict(
            type='str',
            choices=['no_reset', 'day', 'week', 'month', 'month_rolling']),
        description=dict(type='str'),
        tag=dict(type='str'),
        email=dict(type='str'),
        telegram_id=dict(type='int'),
        hwid_device_limit=dict(type='int'),
        internal_squads=dict(type='list', elements='str'),
        external_squad=dict(type='str'),
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
