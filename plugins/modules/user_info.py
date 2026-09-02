#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: user_info
short_description: Retrieve Remnawave users
description:
  - Retrieve one user by username, or list all users of a Remnawave panel.
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
  username:
    description:
      - Return only the user with this username.
      - When omitted, all users are returned.
    type: str
seealso:
  - module: kenyawest.remnawave.user
'''

EXAMPLES = r'''
- name: Get a single user
  kenyawest.remnawave.user_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    username: alice
  register: result

- name: List all users
  kenyawest.remnawave.user_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
  register: result
'''

RETURN = r'''
users:
  description:
    - Matching users as returned by the Remnawave API (camelCase keys).
    - Empty list when a requested username does not exist.
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
    get_user_by_username,
)

PAGE_SIZE = 500


def list_all_users(client):
    users = []
    start = 0
    while True:
        data = client.get('/api/users', query={'start': start, 'size': PAGE_SIZE})
        page = (data or {}).get('users', [])
        users.extend(page)
        total = (data or {}).get('total', len(users))
        start += PAGE_SIZE
        if not page or len(users) >= total:
            return users


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(username=dict(type='str'))
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        if module.params['username']:
            user = get_user_by_username(client, module.params['username'])
            users = [user] if user is not None else []
        else:
            users = list_all_users(client)
        module.exit_json(changed=False, users=users)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
