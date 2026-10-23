#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: infra_provider
short_description: Manage Remnawave infra billing providers
version_added: 1.4.0
description:
  - Create, update and delete the infra billing providers of a Remnawave
    panel - the hosting companies its nodes run at - in a declarative way.
  - Providers are identified by their C(name), which the panel keeps unique.
    Only the options you set are managed.
  - Nodes are linked to a provider through the C(provider) option of
    M(kenyawest.remnawave.node) and M(kenyawest.remnawave.nodes), so create
    the provider first.
  - Deleting a provider unlinks it from its nodes and deletes its billing
    history and billed nodes along with it; this is the panel's doing and
    cannot be undone. The diff of a deletion lists what it takes along.
  - Billing records and the next billing dates of billed nodes describe
    payments rather than configuration and are not managed; use
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
      - Name of the provider, 2 to 30 characters. This is the identifier the
        module searches by; it cannot be changed through this module.
      - An existing provider may also be given by UUID.
    type: str
    required: true
  state:
    description:
      - Whether the provider should exist.
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
      - URL of the provider's control panel or login page. Set to an empty
        string to clear it.
    type: str
seealso:
  - module: kenyawest.remnawave.infra_providers
  - module: kenyawest.remnawave.infra_provider_info
  - module: kenyawest.remnawave.node
'''

EXAMPLES = r'''
- name: Ensure the provider exists
  kenyawest.remnawave.infra_provider:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: Hetzner
    login_url: https://console.hetzner.cloud
    favicon_link: https://www.hetzner.com/favicon.ico

- name: Run a node at it
  kenyawest.remnawave.node:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: de-fsn-1
    provider: Hetzner
'''

RETURN = r'''
provider:
  description:
    - The provider as returned by the Remnawave API (camelCase keys), with
      its C(billingHistory) summary and C(billingNodes).
    - In check mode, the provider as found and changed, or the payload that
      would create it.
  type: dict
  returned: when state=present
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.infra_provider import (
    apply_infra_provider_plan, infra_provider_listings, infra_provider_options,
    plan_infra_provider,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(infra_provider_options())
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        client.prefetch(infra_provider_listings([module.params]))
        plan = plan_infra_provider(module, client, module.params)
        module.exit_json(**apply_infra_provider_plan(module, client, plan))
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
