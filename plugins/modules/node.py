#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: node
short_description: Manage Remnawave nodes
description:
  - Create, update, enable, disable and delete nodes of a Remnawave panel in
    a declarative way.
  - Nodes are identified by their C(name). Only the options you set are
    managed - omitted options are left untouched on the panel.
  - Inbounds are referenced by tag and the config profile by name, and both
    are resolved to UUIDs automatically. Inbound tags are unique across
    profiles, so the config profile may be left out.
  - Hosts bound to the node can be disabled or deleted along with it through
    O(linked_hosts), which covers decommissioning a node without leaving
    dangling subscription entries behind.
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
      - Name of the node. This is the stable identifier the module searches
        by; it cannot be changed through this module.
    type: str
    required: true
  state:
    description:
      - V(present) ensures the node exists and leaves its enabled/disabled
        status alone, so a node disabled in the panel stays disabled.
      - V(enabled) and V(disabled) additionally ensure that status, creating
        the node first if needed.
      - V(absent) deletes the node.
    type: str
    choices: [present, absent, enabled, disabled]
    default: present
  linked_hosts:
    description:
      - What to do with the hosts bound to this node, that is hosts whose
        node binding contains this node.
      - V(ignore) leaves hosts alone.
      - V(enable) and V(disable) apply that status to every linked host, and
        V(delete) removes them. With O(state=absent) the hosts are handled
        before the node is deleted, while the binding can still be resolved.
      - Combine with O(state=present) to act on the linked hosts without
        touching the node itself.
      - Hosts that are not bound to any node are served from every node and
        are therefore never touched by this option.
      - When O(state=absent) and the node does not exist, its former bindings
        cannot be resolved and nothing is cascaded.
    type: str
    choices: [ignore, enable, disable, delete]
    default: ignore
  address:
    description:
      - Address (IP or DNS name) of the node.
      - Required when the node does not exist yet.
    type: str
  port:
    description:
      - Port of the Remnawave node service.
    type: int
  config_profile:
    description:
      - Config profile to activate on the node, by name or UUID.
      - Optional, since it is the profile holding O(inbounds). Set, every
        inbound must belong to it. Requires O(inbounds).
    type: str
  inbounds:
    description:
      - Inbounds to activate on the node, by tag or UUID. Authoritative when
        set.
      - They must all belong to one config profile, which is activated along
        with them. Without O(config_profile) the list must not be empty.
      - Required when the node does not exist yet.
    type: list
    elements: str
  traffic_tracking:
    description:
      - Whether traffic tracking is active on the node.
    type: bool
  traffic_limit:
    description:
      - Traffic limit as a byte count or a human-readable size such as
        V(10TB). Suffix multiples are binary, matching
        C(ansible.builtin.human_to_bytes).
    type: raw
  notify_percent:
    description:
      - Percentage of the traffic limit at which the panel sends a
        notification.
    type: int
  traffic_reset_day:
    description:
      - Day of month on which node traffic statistics are reset.
    type: int
  country_code:
    description:
      - Two-letter country code shown in the panel, or V(XX) for none.
    type: str
  consumption_multiplier:
    description:
      - Multiplier applied to user traffic consumption on this node.
    type: float
  tags:
    description:
      - Tags of the node. Authoritative when set; an empty list removes
        every tag.
      - At most 10 tags, each up to 36 characters of uppercase letters,
        digits, underscores and colons.
    type: list
    elements: str
  note:
    description:
      - Free-form note. Set to an empty string to clear it.
    type: str
  provider:
    description:
      - Infra billing provider the node is hosted at, by name or UUID; see
        M(kenyawest.remnawave.infra_provider). Set to an empty string to
        unlink the node from its provider.
      - Linking a node to a provider does not start billing it; the panel's
        billed nodes and billing records are not managed.
    type: str
    version_added: 1.4.0
seealso:
  - module: kenyawest.remnawave.node_info
  - module: kenyawest.remnawave.host
  - module: kenyawest.remnawave.config_profile
  - module: kenyawest.remnawave.infra_provider
'''

EXAMPLES = r'''
- name: Ensure node exists and is enabled
  kenyawest.remnawave.node:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: nl-ams-1
    state: enabled
    address: 203.0.113.10
    port: 2222
    config_profile: default-profile
    inbounds:
      - vless-reality
    country_code: NL
    provider: Hetzner

- name: Decommission a node together with the hosts bound to it
  kenyawest.remnawave.node:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: nl-ams-1
    state: disabled
    linked_hosts: disable

- name: Disable the hosts of a node without touching the node itself
  kenyawest.remnawave.node:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: nl-ams-1
    state: present
    linked_hosts: disable

- name: Remove a node and every host bound to it
  kenyawest.remnawave.node:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: nl-ams-1
    state: absent
    linked_hosts: delete
'''

RETURN = r'''
node:
  description: The node object as returned by the Remnawave API (camelCase keys).
  type: dict
  returned: when state is not absent
linked_hosts:
  description:
    - Remarks of the hosts bound to this node that were changed (or would be
      changed in check mode) by O(linked_hosts).
  type: list
  elements: str
  returned: when linked_hosts is not ignore
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.node import (
    apply_node_plan, node_listings, node_options, plan_node,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(node_options())
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        client.prefetch(node_listings([module.params]))
        plan = plan_node(module, client, module.params)
        module.exit_json(**apply_node_plan(module, client, plan))
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
