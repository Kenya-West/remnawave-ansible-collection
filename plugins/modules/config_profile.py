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
  - Create, update and delete config profiles (Xray configurations) of a
    Remnawave panel in a declarative way.
  - Profiles are identified by their C(name).
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
      - Name of the config profile. This is the stable identifier the module
        searches by; it cannot be changed through this module.
    type: str
    required: true
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

- name: Remove an old profile
  kenyawest.remnawave.config_profile:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: legacy-profile
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
    exit_with_change, parse_json_option, remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_config_profile,
)


def run(module, client):
    params = module.params
    name = params['name']
    current = find_config_profile(client, name)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.delete('/api/config-profiles/%s' % current['uuid'])
        exit_with_change(module, {'name': name}, {})

    config = parse_json_option(params['config'], 'config', module)

    if current is None:
        if config is None:
            module.fail_json(
                msg='config is required when creating config profile %r' % name)
        payload = {'name': name, 'config': config}
        if module.check_mode:
            exit_with_change(module, {}, payload, profile=payload)
        created = client.post('/api/config-profiles', payload)
        exit_with_change(module, {}, payload, profile=created)

    if config is None or config == current.get('config'):
        module.exit_json(changed=False, profile=current)

    before = {'config': current.get('config')}
    after = {'config': config}
    if module.check_mode:
        exit_with_change(module, before, after, profile=current)
    updated = client.patch(
        '/api/config-profiles', {'uuid': current['uuid'], 'config': config})
    exit_with_change(module, before, after, profile=updated)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        config=dict(type='raw'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
