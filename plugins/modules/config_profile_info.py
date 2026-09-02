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
  - Retrieve one config profile by name, or list all config profiles of a
    Remnawave panel, including their parsed inbounds (tags and UUIDs).
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
      - When omitted, all profiles are returned.
    type: str
seealso:
  - module: kenyawest.remnawave.config_profile
'''

EXAMPLES = r'''
- name: List config profiles with their inbounds
  kenyawest.remnawave.config_profile_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
  register: result
'''

RETURN = r'''
profiles:
  description: Matching config profiles as returned by the Remnawave API.
  type: list
  elements: dict
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_config_profile, list_config_profiles,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(name=dict(type='str'))
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        if module.params['name']:
            profile = find_config_profile(client, module.params['name'])
            profiles = [profile] if profile is not None else []
        else:
            profiles = list_config_profiles(client)
        module.exit_json(changed=False, profiles=profiles)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
