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
  - The config profile is referenced by name and inbounds by tag; both are
    resolved to UUIDs automatically.
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
      - Required when the node does not exist yet.
    type: str
  inbounds:
    description:
      - Inbounds of the config profile to activate on the node, by tag or
        UUID. Authoritative when set.
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
      - Tags of the node. Authoritative when set.
    type: list
    elements: str
  note:
    description:
      - Free-form note. Set to an empty string to clear it.
    type: str
seealso:
  - module: kenyawest.remnawave.node_info
  - module: kenyawest.remnawave.host
  - module: kenyawest.remnawave.config_profile
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
    STATE_CHOICES, FieldSpec, build_patch, desired_enabled, exit_with_change,
    parse_traffic_limit, remnawave_argument_spec, resolve_for_check_mode,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    bulk_host_action, find_node, hosts_linked_to_node, resolve_inbound_uuids,
)


def current_config_profile(value):
    value = value or {}
    return {
        'activeConfigProfileUuid': value.get('activeConfigProfileUuid'),
        'activeInbounds': sorted(
            i.get('uuid') for i in (value.get('activeInbounds') or [])),
    }


def build_fields(module, client):
    params = module.params
    fields = [
        FieldSpec('address', 'address'),
        FieldSpec('port', 'port'),
        FieldSpec('traffic_tracking', 'isTrafficTrackingActive'),
        FieldSpec('traffic_limit', 'trafficLimitBytes',
                  to_api=parse_traffic_limit),
        FieldSpec('notify_percent', 'notifyPercent'),
        FieldSpec('traffic_reset_day', 'trafficResetDay'),
        FieldSpec('country_code', 'countryCode', to_api=lambda v: v.upper()),
        FieldSpec('consumption_multiplier', 'consumptionMultiplier'),
        FieldSpec('tags', 'tags', kind='set'),
        FieldSpec('note', 'note', to_api=lambda v: v or None),
    ]
    resolved = dict(params)
    if params['config_profile'] is not None or params['inbounds'] is not None:
        if params['config_profile'] is None or params['inbounds'] is None:
            module.fail_json(
                msg='config_profile and inbounds must be set together')
        profile_uuid, inbound_uuids = resolve_for_check_mode(
            module,
            lambda: resolve_inbound_uuids(
                client, params['config_profile'], params['inbounds']),
            (params['config_profile'], list(params['inbounds'])))
        resolved['config_profile'] = {
            'activeConfigProfileUuid': profile_uuid,
            'activeInbounds': sorted(inbound_uuids),
        }
        fields.append(FieldSpec(
            'config_profile', 'configProfile', kind='json',
            from_api=current_config_profile))
    return fields, resolved


def apply_enabled(module, client, current, wanted):
    """Reconcile the enable/disable action; returns True when it changed."""
    if wanted is None or current is None:
        return False
    currently_enabled = not current.get('isDisabled', False)
    if currently_enabled == wanted:
        return False
    if not module.check_mode:
        action = 'enable' if wanted else 'disable'
        client.post('/api/nodes/%s/actions/%s' % (current['uuid'], action))
    return True


def cascade_hosts(module, client, node, before, after):
    """Apply the linked_hosts action; returns the affected host remarks."""
    action = module.params['linked_hosts']
    if action == 'ignore' or node is None:
        return []

    linked = hosts_linked_to_node(client, node['uuid'])
    if action == 'delete':
        targets = linked
    else:
        wanted_disabled = (action == 'disable')
        targets = [h for h in linked
                   if bool(h.get('isDisabled', False)) != wanted_disabled]
    if not targets:
        return []

    remarks = sorted(h.get('remark') for h in targets)
    before['linkedHosts'] = dict(
        (h.get('remark'), 'disabled' if h.get('isDisabled') else 'enabled')
        for h in targets)
    after['linkedHosts'] = dict(
        (h.get('remark'), 'absent' if action == 'delete' else '%sd' % action)
        for h in targets)

    if not module.check_mode:
        bulk_host_action(client, action, [h['uuid'] for h in targets])
    return remarks


def run(module, client):
    params = module.params
    name = params['name']
    state = params['state']
    current = find_node(client, name)
    before, after = {}, {}

    if state == 'absent':
        if current is None:
            # Without the node there is no binding left to resolve, so any
            # cascade would have to guess which hosts were linked.
            module.exit_json(changed=False, linked_hosts=[])
        # Hosts first: after the node is gone the binding cannot be resolved.
        remarks = cascade_hosts(module, client, current, before, after)
        if not module.check_mode:
            client.delete('/api/nodes/%s' % current['uuid'])
        before['name'] = name
        exit_with_change(module, before, after, linked_hosts=remarks)

    wanted_enabled = desired_enabled(state)
    fields, resolved = build_fields(module, client)
    patch, patch_before, patch_after = build_patch(resolved, current, fields)
    before.update(patch_before)
    after.update(patch_after)

    if current is None:
        missing = [opt for opt in ('address', 'config_profile', 'inbounds')
                   if params[opt] is None]
        if missing:
            module.fail_json(
                msg='Creating node %r requires: %s' % (name, ', '.join(missing)))
        payload = dict(patch)
        payload['name'] = name
        after['name'] = name
        if wanted_enabled is False:
            after['isDisabled'] = True
        if module.check_mode:
            exit_with_change(module, before, after, node=payload, linked_hosts=[])
        created = client.post('/api/nodes', payload)
        # Nodes are created enabled; honour state=disabled immediately.
        if wanted_enabled is False:
            client.post('/api/nodes/%s/actions/disable' % created['uuid'])
            created = find_node(client, name, required=True)
        # A brand new node cannot have hosts bound to it yet.
        exit_with_change(module, before, after, node=created, linked_hosts=[])

    enabled_changed = apply_enabled(module, client, current, wanted_enabled)
    if enabled_changed:
        before['isDisabled'] = current.get('isDisabled')
        after['isDisabled'] = not wanted_enabled

    if patch:
        payload = dict(patch)
        payload['uuid'] = current['uuid']
        if not module.check_mode:
            client.patch('/api/nodes', payload)

    remarks = cascade_hosts(module, client, current, before, after)

    if not patch and not enabled_changed and not remarks:
        module.exit_json(changed=False, node=current, linked_hosts=[])

    node = current if module.check_mode else find_node(client, name, required=True)
    exit_with_change(module, before, after, node=node, linked_hosts=remarks)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=STATE_CHOICES, default='present'),
        linked_hosts=dict(type='str', default='ignore',
                          choices=['ignore', 'enable', 'disable', 'delete']),
        address=dict(type='str'),
        port=dict(type='int'),
        config_profile=dict(type='str'),
        inbounds=dict(type='list', elements='str'),
        traffic_tracking=dict(type='bool'),
        traffic_limit=dict(type='raw'),
        notify_percent=dict(type='int'),
        traffic_reset_day=dict(type='int'),
        country_code=dict(type='str'),
        consumption_multiplier=dict(type='float'),
        tags=dict(type='list', elements='str'),
        note=dict(type='str'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
