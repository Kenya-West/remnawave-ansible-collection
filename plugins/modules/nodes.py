#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: nodes
short_description: Manage many Remnawave nodes in one task
version_added: 1.3.0
description:
  - Create, update, enable, disable and delete a list of nodes of a Remnawave
    panel in a declarative way, in a single task.
  - Every entry of O(nodes) takes the options of M(kenyawest.remnawave.node)
    and means the same thing. The difference is speed. A loop of
    M(kenyawest.remnawave.node) is one module run per node, and each run
    reads the panel's nodes and config profiles again and writes one node
    at a time. This module reads each listing once for the whole list, all
    at the same time, and writes only what needs a change, in as few
    requests as it can, several at a time.
  - Every entry is planned before anything is written. An entry that cannot
    be applied - an unknown config profile or inbound, a node missing what
    its creation requires - fails the task and nothing is changed.
  - Entries are planned against the panel as it is when the task starts. One
    entry therefore cannot rely on another entry's change, and a node may be
    declared only once. Nor may two entries give a host bound to both of
    their nodes different O(nodes[].linked_hosts) actions.
  - Writes go in this order. The hosts of O(nodes[].linked_hosts), in one
    request per action, so that they are handled while the binding of a
    node to delete can still be resolved. Nodes to delete. Nodes to enable
    and to disable, in one request each. Nodes to update; those given
    exactly the same change of the fields the panel can set on many nodes
    at once - O(nodes[].country_code), O(nodes[].consumption_multiplier),
    O(nodes[].tags), O(nodes[].note), O(nodes[].provider), or the config
    profile and inbounds - are updated together in one request. Nodes to create. Then the nodes
    created with O(nodes[].state=disabled) are disabled, in one request.
    Each step sends up to O(parallelism) requests at once; creations do so
    with O(ordered) only, and otherwise go one at a time in list order.
  - With O(ordered), one more request then puts the listed nodes in list
    order. If anything was written, the nodes are read again once, to
    report them as they are.
  - If the panel rejects a write, the task fails and writes nothing more.
    Writes already made stay applied, and RV(results) lists the entries
    carried out in full. With O(parallelism) above 1, writes running
    alongside the rejected one may have been carried out as well.
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
        diff per changed node.
    support: full
options:
  parallelism:
    description:
      - How many requests of one step may run at the same time.
      - V(1) sends them one after another.
    type: int
    default: 4
  ordered:
    description:
      - Arrange the nodes of O(nodes) in the panel in the order they are
        listed, in one reorder request after all other writes, and only
        when they are not in that order already.
      - The listed nodes trade places among themselves. Nodes of the panel
        that are not listed keep theirs, so a node placed by hand between
        two listed ones stays between them. New nodes take places after
        the existing ones before they are put in order.
      - A node that only changes place is reported with RV(results[].action)
        V(update), and its diff shows its C(viewPosition).
      - V(false) leaves the order of the panel's nodes alone.
    type: bool
    default: true
  nodes:
    description:
      - The nodes to manage, each with the options of
        M(kenyawest.remnawave.node).
      - An empty list manages nothing. Nodes of the panel that are not listed
        are left alone.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description:
          - Name of the node, which identifies it on the panel.
        type: str
        required: true
      state:
        description:
          - V(present) ensures the node exists and leaves its enabled/disabled
            status alone, V(enabled) and V(disabled) ensure that status as
            well, creating the node first if needed, and V(absent) deletes
            it.
        type: str
        choices: [present, absent, enabled, disabled]
        default: present
      linked_hosts:
        description:
          - What to do with the hosts bound to this node - V(ignore) them,
            V(enable), V(disable) or V(delete) them.
          - Hosts not bound to any node are served from every node and never
            touched. When the node does not exist, nothing is cascaded.
        type: str
        choices: [ignore, enable, disable, delete]
        default: ignore
      address:
        description:
          - Address (IP or DNS name) of the node. Required when the node does
            not exist yet.
        type: str
      port:
        description:
          - Port of the Remnawave node service.
        type: int
      config_profile:
        description:
          - Config profile to activate on the node, by name or UUID.
          - Optional, since it is the profile holding O(nodes[].inbounds).
            Requires O(nodes[].inbounds).
        type: str
      inbounds:
        description:
          - Inbounds to activate on the node, by tag or UUID. Authoritative
            when set; they must all belong to one config profile.
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
            V(10TB).
        type: raw
      notify_percent:
        description:
          - Percentage of the traffic limit at which the panel notifies.
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
        type: list
        elements: str
      note:
        description:
          - Free-form note. Set to an empty string to clear it.
        type: str
      provider:
        description:
          - Infra billing provider the node is hosted at, by name or UUID.
            Set to an empty string to unlink the node from its provider.
        type: str
        version_added: 1.4.0
seealso:
  - module: kenyawest.remnawave.node
  - module: kenyawest.remnawave.node_info
  - module: kenyawest.remnawave.hosts
  - module: kenyawest.remnawave.infra_providers
'''

EXAMPLES = r'''
- name: Publish every node of the inventory, new ones disabled, in one task
  kenyawest.remnawave.nodes:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    nodes:
      - name: nl-ams-1
        state: enabled
        address: 203.0.113.10
        port: 2222
        inbounds: [vless-reality]
        country_code: NL
      - name: de-fra-1
        state: disabled
        address: 203.0.113.20
        port: 2222
        inbounds: [vless-reality]
        country_code: DE

- name: Tag every node the same way, in one request
  kenyawest.remnawave.nodes:
    nodes: "{{ node_names | map('community.general.dict_kv', 'name')
               | map('combine', {'tags': ['PROD']}) | list }}"

- name: Retire nodes, disabling the hosts bound to them
  kenyawest.remnawave.nodes:
    nodes: "{{ retired_nodes | map('community.general.dict_kv', 'name')
               | map('combine', {'state': 'absent', 'linked_hosts': 'disable'})
               | list }}"
  register: retired

- name: Report the nodes that were actually deleted
  ansible.builtin.debug:
    msg: "{{ retired.results | selectattr('changed') | map(attribute='name') | list }}"
'''

RETURN = r'''
results:
  description:
    - One item per entry of O(nodes), in the same order.
    - When the task fails part way, only the entries carried out in full.
  type: list
  elements: dict
  returned: always
  contains:
    name:
      description: The name of the node.
      type: str
      returned: always
    action:
      description:
        - What was (or, in check mode, would be) done to the node -
          V(create), V(update), V(delete) or V(none).
        - Enabling and disabling a node is an V(update), and so is moving it
          into list order (O(ordered)). Changing only its linked hosts is
          V(none), with RV(results[].changed) true.
      type: str
      returned: always
    changed:
      description: Whether this node or its linked hosts changed.
      type: bool
      returned: always
    linked_hosts:
      description:
        - Remarks of the hosts bound to this node that were changed (or would
          be in check mode) by O(nodes[].linked_hosts).
      type: list
      elements: str
      returned: always
    node:
      description:
        - The node object as returned by the Remnawave API (camelCase keys).
        - In check mode, the node as found, or the payload that would create
          it.
      type: dict
      returned: unless the node is, or would be, absent
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.node import (
    DEFAULT_PARALLELISM, apply_node_plans, arrange_nodes, node_options,
    plan_nodes, refresh_nodes,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    list_nodes,
)


def run(module, client):
    try:
        plans = plan_nodes(module, client, module.params['nodes'])
    except RemnawaveApiError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc,
                         status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc)

    ordered = module.params['ordered']
    # The nodes as planning found them, read before the writes drop them
    # from the client's cache.
    listing = list_nodes(client) if ordered else None
    applied, failure = apply_node_plans(module, client, plans,
                                        module.params['parallelism'], ordered)
    if failure:
        failed, exc = failure
        failure = (', '.join(p['label'] for p in failed), exc)
    elif ordered:
        exc = arrange_nodes(module, client, plans, applied, listing)
        if exc is not None:
            failure = ('Putting the nodes in list order', exc)
    if (not failure and not module.check_mode
            and any(r['changed'] for r in applied)):
        refresh_nodes(client, applied)

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
        result.setdefault('action', plan['action'])
        results.append(result)

    output = dict(changed=any(r['changed'] for r in results), results=results)
    if diffs:
        output['diff'] = diffs
    if failure:
        label, exc = failure
        module.fail_json(msg='%s: %s' % (label, exc), status=exc.status,
                         error_code=exc.error_code, **output)
    module.exit_json(**output)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        parallelism=dict(type='int', default=DEFAULT_PARALLELISM),
        ordered=dict(type='bool', default=True),
        nodes=dict(type='list', elements='dict', required=True,
                   options=node_options()),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    if module.params['parallelism'] < 1:
        module.fail_json(msg='parallelism must be at least 1')

    client = RemnawaveClient(module)
    run(module, client)


if __name__ == '__main__':
    main()
