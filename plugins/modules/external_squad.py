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
  - Create and delete external squads of a Remnawave panel.
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
    exit_with_change, remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_external_squad,
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

    if current is not None:
        module.exit_json(changed=False, squad=current)

    payload = {'name': name}
    if module.check_mode:
        exit_with_change(module, {}, payload, squad=payload)
    created = client.post('/api/external-squads', payload)
    exit_with_change(module, {}, payload, squad=created)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
