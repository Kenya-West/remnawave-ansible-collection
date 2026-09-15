#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: config_profile_info
short_description: Retrieve Remnawave config profiles
description:
  - Retrieve one config profile by name or by the tag of one of its inbounds,
    or list all config profiles of a Remnawave panel, including their parsed
    inbounds (tags and UUIDs).
  - The inbounds of the returned profiles are also listed on their own in
    RV(inbounds), each with the UUID and name of its profile, which is the
    way to turn an inbound tag into the UUIDs the API uses.
  - This module never changes anything and always returns C(changed=false).
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
    support: none
options:
  name:
    description:
      - Return only the config profile with this name.
      - When neither O(name) nor O(inbound) is set, all profiles are returned.
    type: str
  inbound:
    description:
      - Return only the config profile holding the inbound with this tag (or
        UUID), and in RV(inbounds) only that inbound.
    type: str
    version_added: 1.3.0
seealso:
  - module: kenyawest.remnawave.config_profile
'''

EXAMPLES = r'''
- name: List config profiles with their inbounds
  kenyawest.remnawave.config_profile_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
  register: result

- name: Look up the UUIDs behind an inbound tag
  kenyawest.remnawave.config_profile_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    inbound: vless-reality
  register: found

- name: Use them
  ansible.builtin.debug:
    msg: >-
      inbound {{ found.inbounds[0].uuid }} belongs to config profile
      {{ found.inbounds[0].profileName }} ({{ found.inbounds[0].profileUuid }})
  when: found.inbounds | length > 0
'''

RETURN = r'''
profiles:
  description: Matching config profiles as returned by the Remnawave API.
  type: list
  elements: dict
  returned: always
inbounds:
  description:
    - The inbounds of the returned config profiles, or with O(inbound) only
      the matching inbound. Empty when nothing matches.
    - Each is the inbound as returned by the Remnawave API, plus the name of
      its config profile.
  type: list
  elements: dict
  returned: always
  version_added: 1.3.0
  contains:
    uuid:
      description: UUID of the inbound.
      type: str
    tag:
      description: Tag of the inbound.
      type: str
    profileUuid:
      description: UUID of the config profile holding the inbound.
      type: str
    profileName:
      description: Name of the config profile holding the inbound.
      type: str
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_config_profile, find_inbounds, inbound_view, list_config_profiles,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
        inbound=dict(type='str'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[('name', 'inbound')],
    )
    params = module.params

    client = RemnawaveClient(module)
    try:
        if params['inbound']:
            # Tags are unique on the panel, but an info module reports every
            # match rather than judging them.
            matches = find_inbounds(client, params['inbound'])
            profiles = []
            for profile, dummy in matches:
                if all(p['uuid'] != profile['uuid'] for p in profiles):
                    profiles.append(profile)
            inbounds = [inbound_view(p, i) for p, i in matches]
        else:
            if params['name']:
                profile = find_config_profile(client, params['name'])
                profiles = [profile] if profile is not None else []
            else:
                profiles = list_config_profiles(client)
            inbounds = [inbound_view(p, i) for p in profiles
                        for i in p.get('inbounds') or []]
        module.exit_json(changed=False, profiles=profiles, inbounds=inbounds)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
