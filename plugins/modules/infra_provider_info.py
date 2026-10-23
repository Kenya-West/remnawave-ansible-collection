#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: infra_provider_info
short_description: Retrieve Remnawave infra billing providers
version_added: 1.4.0
description:
  - Retrieve one infra billing provider by name or UUID, or list all
    providers of a Remnawave panel, with their billing summaries and the
    nodes linked to them.
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
      - Return only the provider with this name or UUID.
      - When omitted, all providers are returned.
    type: str
seealso:
  - module: kenyawest.remnawave.infra_provider
  - module: kenyawest.remnawave.node_info
'''

EXAMPLES = r'''
- name: List infra providers
  kenyawest.remnawave.infra_provider_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
  register: result

- name: Show what each provider has been paid in total
  ansible.builtin.debug:
    msg: "{{ result.providers | items2dict(key_name='name', value_name='billingHistory') }}"
'''

RETURN = r'''
providers:
  description:
    - Matching providers as returned by the Remnawave API (camelCase keys),
      each with its C(billingHistory) summary and C(billingNodes).
  type: list
  elements: dict
  returned: always
nodes:
  description:
    - Names of the nodes linked to each returned provider, by provider name.
  type: dict
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
    find_infra_provider, list_infra_providers, list_nodes,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(name=dict(type='str'))
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        client.prefetch(['/api/infra-billing/providers', '/api/nodes'])
        if module.params['name']:
            provider = find_infra_provider(client, module.params['name'])
            providers = [provider] if provider is not None else []
        else:
            providers = list_infra_providers(client)
        nodes = dict((p['name'], sorted(
            n.get('name') for n in list_nodes(client)
            if n.get('providerUuid') == p['uuid'])) for p in providers)
        module.exit_json(changed=False, providers=providers, nodes=nodes)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
