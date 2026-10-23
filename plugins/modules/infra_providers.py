#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: infra_providers
short_description: Manage many Remnawave infra billing providers in one task
version_added: 1.4.0
description:
  - Create, update and delete a list of infra billing providers of a
    Remnawave panel in a declarative way, in a single task.
  - Every entry of O(providers) takes the options of
    M(kenyawest.remnawave.infra_provider) and means the same thing. This
    module reads the providers once for the whole list and writes only what
    needs a change, several requests at a time.
  - Every entry is planned before anything is written. An entry that cannot
    be applied - a name the panel would refuse, a provider declared twice -
    fails the task and nothing is changed.
  - Providers to delete go first, then those to update and to create. Each
    step sends up to O(parallelism) requests at once. The panel keeps no
    order of providers, so none is managed.
  - If the panel rejects a write, the task fails and writes nothing more.
    Writes already made stay applied, and RV(results) lists the entries
    carried out in full. If anything was written, the providers are read
    again once, to report them as they are.
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
      - Returns what changed (or would change) when run with C(--diff), one
        diff per changed provider.
    support: full
options:
  parallelism:
    description:
      - How many requests of one step may run at the same time.
      - V(1) sends them one after another.
    type: int
    default: 4
  providers:
    description:
      - The providers to manage, each with the options of
        M(kenyawest.remnawave.infra_provider).
      - An empty list manages nothing. Providers of the panel that are not
        listed are left alone.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description:
          - Name of the provider, 2 to 30 characters, which identifies it on
            the panel. An existing provider may also be given by UUID.
        type: str
        required: true
      state:
        description:
          - Whether the provider should exist. Deleting a provider unlinks it
            from its nodes and deletes its billing history and billed nodes.
        type: str
        choices: [present, absent]
        default: present
      favicon_link:
        description:
          - URL of the icon the panel shows for the provider. Set to an empty
            string to clear it.
        type: str
      login_url:
        description:
          - URL of the provider's control panel or login page. Set to an
            empty string to clear it.
        type: str
seealso:
  - module: kenyawest.remnawave.infra_provider
  - module: kenyawest.remnawave.infra_provider_info
  - module: kenyawest.remnawave.nodes
'''

EXAMPLES = r'''
- name: Declare every provider the fleet runs at
  kenyawest.remnawave.infra_providers:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    providers:
      - name: Hetzner
        login_url: https://console.hetzner.cloud
      - name: OVHcloud
        login_url: https://www.ovh.com/manager
      - name: Retired Host
        state: absent

- name: Then link the nodes to them
  kenyawest.remnawave.nodes:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    nodes:
      - name: de-fsn-1
        provider: Hetzner
      - name: fr-gra-1
        provider: OVHcloud
'''

RETURN = r'''
results:
  description:
    - One item per entry of O(providers), in the same order.
    - When the task fails part way, only the entries carried out in full.
  type: list
  elements: dict
  returned: always
  contains:
    name:
      description: The name of the provider, as given.
      type: str
      returned: always
    action:
      description:
        - What was (or, in check mode, would be) done to the provider -
          V(create), V(update), V(delete) or V(none).
      type: str
      returned: always
    changed:
      description: Whether this provider changed.
      type: bool
      returned: always
    provider:
      description:
        - The provider as returned by the Remnawave API (camelCase keys).
        - In check mode, the provider as found and changed, or the payload
          that would create it.
      type: dict
      returned: unless the provider is, or would be, absent
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.infra_provider import (
    DEFAULT_PARALLELISM, apply_infra_provider_plans, infra_provider_options,
    plan_infra_providers, refresh_infra_providers,
)


def run(module, client):
    try:
        plans = plan_infra_providers(module, client, module.params['providers'])
    except RemnawaveApiError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc,
                         status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc)

    applied, failure = apply_infra_provider_plans(
        module, client, plans, module.params['parallelism'])
    if (not failure and not module.check_mode
            and any(r['changed'] for r in applied)):
        refresh_infra_providers(client, applied)

    results = []
    diffs = []
    for plan, result in zip(plans, applied):
        if result is None:
            continue
        diff = result.pop('diff', None)
        if diff is not None:
            diffs.append(dict(diff, before_header=plan['label'],
                              after_header=plan['label']))
        result['name'] = plan['name']
        result['action'] = plan['action']
        results.append(result)

    output = dict(changed=any(r['changed'] for r in results), results=results)
    if diffs:
        output['diff'] = diffs
    if failure:
        failed, exc = failure
        module.fail_json(msg='%s: %s' % (', '.join(p['label'] for p in failed), exc),
                         status=exc.status, error_code=exc.error_code, **output)
    module.exit_json(**output)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        parallelism=dict(type='int', default=DEFAULT_PARALLELISM),
        providers=dict(type='list', elements='dict', required=True,
                       options=infra_provider_options()),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    if module.params['parallelism'] < 1:
        module.fail_json(msg='parallelism must be at least 1')

    client = RemnawaveClient(module)
    run(module, client)


if __name__ == '__main__':
    main()
