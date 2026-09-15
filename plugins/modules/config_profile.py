#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: config_profile
short_description: Manage Remnawave config profiles
description:
  - Create, update, rename and delete config profiles (Xray configurations)
    of a Remnawave panel in a declarative way.
  - Profiles are identified by their C(name), or by the tag of one of their
    inbounds when O(inbound) is set. The panel keeps inbound tags unique
    across all profiles, and a tag is written in the config itself, which
    makes it the more stable identifier of the two.
  - The supplied O(config) is treated as authoritative - the profile's stored
    configuration is made exactly equal to it.
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
      - Name of the config profile.
      - Without O(inbound), this is the identifier the module searches by; it
        cannot be changed that way.
      - With O(inbound), it is an ordinary managed field. Set, it renames the
        profile found by its inbound. It is required to create a profile.
      - At least one of O(name) and O(inbound) is required.
    type: str
  inbound:
    description:
      - Tag (or UUID) of an inbound of the config profile. When set, the
        profile holding this inbound is the one managed, whatever its name.
      - Nothing else is needed to address a profile this way, for example to
        retag or delete it.
      - When O(config) is set as well, it must still declare an inbound with
        this tag, otherwise the next run could not find the profile again. To
        remove or rename the identifying inbound, address the profile by
        O(name).
      - A profile can be created by its inbound tag, given O(name) and
        O(config), but not by an inbound UUID, since the panel assigns those.
    type: str
    version_added: 1.3.0
  state:
    description:
      - Whether the profile should exist.
    type: str
    choices: [present, absent]
    default: present
  config:
    description:
      - The Xray configuration as a dict or a JSON-encoded string.
      - Required when the profile does not exist yet.
    type: raw
  tags:
    description:
      - Tags of the config profile. Authoritative when set; an empty list
        removes every tag.
      - At most 10 tags, each up to 36 characters of uppercase letters,
        digits, underscores and colons.
      - Not to be confused with the inbound tag in O(inbound).
    type: list
    elements: str
    version_added: 1.2.0
seealso:
  - module: kenyawest.remnawave.config_profile_info
  - module: kenyawest.remnawave.node
'''

EXAMPLES = r'''
- name: Ensure config profile matches the file in the repository
  kenyawest.remnawave.config_profile:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: default-profile
    state: present
    config: "{{ lookup('ansible.builtin.file', 'files/xray-config.json') }}"
    tags:
      - PRODUCTION
      - REGION:EU

- name: Tag the profile serving the vless-reality inbound, whatever it is called
  kenyawest.remnawave.config_profile:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    inbound: vless-reality
    tags:
      - PRODUCTION

- name: Rename that profile
  kenyawest.remnawave.config_profile:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    inbound: vless-reality
    name: eu-profile

- name: Remove an old profile
  kenyawest.remnawave.config_profile:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: legacy-profile
    state: absent

- name: Remove the profile holding a retired inbound
  kenyawest.remnawave.config_profile:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    inbound: legacy-trojan
    state: absent
'''

RETURN = r'''
profile:
  description:
    - The config profile as returned by the Remnawave API, including the
      parsed inbounds with their tags and UUIDs.
  type: dict
  returned: when state=present
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    exit_with_change, is_uuid, normalize_xray_config, parse_json_option,
    remnawave_argument_spec, tags_differ, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_config_profile, find_inbound, set_tags,
)


def declared_inbound_tags(config):
    """Tags of the inbounds a config declares."""
    if not isinstance(config, dict):
        return []
    return [i.get('tag') for i in config.get('inbounds') or []
            if isinstance(i, dict)]


def find_current(client, params):
    if params['inbound'] is None:
        return find_config_profile(client, params['name'])
    return find_inbound(client, params['inbound'])[0]


def check_identifiers(module, client, params, current, config):
    """Refuse what would lose or collide with the profile's identifiers."""
    name, inbound = params['name'], params['inbound']
    if inbound is None:
        return

    if (config is not None and not is_uuid(inbound)
            and inbound not in declared_inbound_tags(config)):
        module.fail_json(
            msg='config declares no inbound tagged %r, which identifies this '
                'config profile, so the next run would not find the profile '
                'again. To remove or rename that inbound, address the profile '
                'by name' % inbound)

    if name is None:
        return
    named = find_config_profile(client, name)
    if named is None or (current is not None and named['uuid'] == current['uuid']):
        return
    if current is None:
        module.fail_json(
            msg='Config profile %r already exists but has no inbound %r. Add '
                'the inbound to its config while addressing the profile by '
                'name, then address it by the inbound' % (name, inbound))
    module.fail_json(
        msg='Cannot rename config profile %r to %r: another config profile '
            'already has that name' % (current.get('name'), name))


def run(module, client):
    params = module.params
    name, inbound = params['name'], params['inbound']
    current = find_current(client, params)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.delete('/api/config-profiles/%s' % current['uuid'])
        exit_with_change(module, {'name': current.get('name')}, {})

    config = parse_json_option(params['config'], 'config', module)
    tags = validate_tags(params['tags'])
    check_identifiers(module, client, params, current, config)

    if current is None:
        if inbound is not None and is_uuid(inbound):
            module.fail_json(
                msg='No config profile has an inbound with UUID %r; a profile '
                    'can be created by an inbound tag, not by a UUID' % inbound)
        if name is None:
            module.fail_json(
                msg='No config profile has an inbound %r; name is required to '
                    'create one' % inbound)
        if config is None:
            module.fail_json(
                msg='config is required when creating config profile %r' % name)
        payload = {'name': name, 'config': config}
        after = dict(payload)
        if tags:
            after['tags'] = tags
        if module.check_mode:
            exit_with_change(module, {}, after, profile=after)
        created = client.post('/api/config-profiles', payload)
        # Tags are not part of the create body; they have their own endpoint.
        if tags:
            created = set_tags(client, 'config-profiles', created, tags)
        exit_with_change(module, {}, after, profile=created)

    before, after, payload = {}, {}, {}
    # Only a profile found by its inbound can be renamed: found by name, the
    # name is already equal (or was a UUID, which is no name to rename to).
    if inbound is not None and name is not None and name != current.get('name'):
        before['name'] = current.get('name')
        after['name'] = payload['name'] = name
    if (config is not None and normalize_xray_config(config)
            != normalize_xray_config(current.get('config'))):
        before['config'] = current.get('config')
        after['config'] = payload['config'] = config
    tags_changed = tags_differ(tags, current.get('tags'))
    if tags_changed:
        before['tags'] = current.get('tags') or []
        after['tags'] = tags

    if not payload and not tags_changed:
        module.exit_json(changed=False, profile=current)
    if module.check_mode:
        exit_with_change(module, before, after, profile=current)

    profile = current
    if payload:
        payload['uuid'] = current['uuid']
        profile = client.patch('/api/config-profiles', payload)
    if tags_changed:
        profile = set_tags(client, 'config-profiles', profile or current, tags)
    exit_with_change(module, before, after, profile=profile)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
        inbound=dict(type='str'),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        config=dict(type='raw'),
        tags=dict(type='list', elements='str'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_one_of=[('name', 'inbound')],
    )

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
