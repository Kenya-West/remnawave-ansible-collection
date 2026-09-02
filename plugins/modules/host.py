#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: host
short_description: Manage Remnawave subscription hosts
description:
  - Create, update, enable, disable and delete hosts (subscription entries)
    of a Remnawave panel in a declarative way.
  - Hosts are identified by their C(remark) by default, or by their
    C(address) when O(identify_by=address) - useful when the domain, not the
    display name, is what your data is keyed by.
  - Whichever identifier is used must match at most one host; the module
    fails rather than guessing when several hosts share it.
  - The inbound is referenced by config profile name and inbound tag and
    resolved to UUIDs automatically.
  - Advanced host properties not covered by this module (mux, sockopt,
    mappers, subscription mappers and so on) can be managed with
    M(kenyawest.remnawave.api).
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
  identify_by:
    description:
      - Which option identifies the host on the panel.
      - V(remark) (the default) searches by O(remark), the host's display
        name.
      - V(address) searches by O(address) instead, so playbooks driven by a
        list of domains need not invent remarks. O(remark) then becomes an
        ordinary managed field and may be used to rename the host.
      - The identifying option must match at most one host. Addresses are not
        unique in Remnawave - one domain can serve several inbounds or ports -
        so the module fails on ambiguity instead of picking one.
    type: str
    choices: [remark, address]
    default: remark
  remark:
    description:
      - Remark (display name) of the host.
      - Required and used as the identifier unless O(identify_by=address);
        it cannot be changed while it is the identifier.
      - With O(identify_by=address) it is optional. Set, it renames the host.
        Omitted, a newly created host gets its address as its remark.
    type: str
  state:
    description:
      - V(present) ensures the host exists and leaves its enabled/disabled
        status alone, so a host disabled in the panel stays disabled.
      - V(enabled) and V(disabled) additionally ensure that status, creating
        the host first if needed.
      - V(absent) deletes the host.
    type: str
    choices: [present, absent, enabled, disabled]
    default: present
  nodes:
    description:
      - Nodes this host is bound to, by name or UUID. Authoritative when set.
      - An empty list unbinds the host, which makes the panel serve it from
        every node. Hosts bound to no node are never affected by the
        O(kenyawest.remnawave.node#module:linked_hosts) cascade.
    type: list
    elements: str
  config_profile:
    description:
      - Config profile the host's inbound belongs to, by name or UUID.
      - Required when the host does not exist yet.
    type: str
  inbound:
    description:
      - Inbound of the config profile, by tag or UUID.
      - Required when the host does not exist yet.
    type: str
  address:
    description:
      - Address (domain or IP) advertised to clients.
      - Required when the host does not exist yet, and always required with
        O(identify_by=address), where it is also the identifier.
    type: str
  port:
    description:
      - Port advertised to clients.
      - Required when the host does not exist yet.
    type: int
  path:
    description:
      - Path (for websocket/xhttp style transports).
    type: str
  sni:
    description:
      - SNI advertised to clients.
    type: str
  host_header:
    description:
      - Value of the C(Host) header advertised to clients (the API field
        C(host)).
    type: str
  alpn:
    description:
      - ALPN value.
    type: str
    choices: ['h3', 'h2', 'http/1.1', 'h2,http/1.1', 'h3,h2,http/1.1', 'h3,h2']
  fingerprint:
    description:
      - uTLS fingerprint, for example V(chrome).
    type: str
  security_layer:
    description:
      - Security layer override.
    type: str
    choices: [default, tls, none]
  hidden:
    description:
      - Whether the host is hidden from subscriptions.
    type: bool
  tags:
    description:
      - Tags of the host. Authoritative when set.
    type: list
    elements: str
  server_description:
    description:
      - Server description shown in some clients. Set to an empty string to
        clear it.
    type: str
seealso:
  - module: kenyawest.remnawave.host_info
  - module: kenyawest.remnawave.node
  - module: kenyawest.remnawave.config_profile
'''

EXAMPLES = r'''
- name: Ensure a host exists, bound to two nodes
  kenyawest.remnawave.host:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    remark: Amsterdam
    state: enabled
    config_profile: default-profile
    inbound: vless-reality
    address: ams.example.com
    port: 443
    sni: ams.example.com
    fingerprint: chrome
    nodes:
      - nl-ams-1
      - nl-ams-2

- name: Temporarily disable a host
  kenyawest.remnawave.host:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    remark: Amsterdam
    state: disabled

- name: Remove a host
  kenyawest.remnawave.host:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    remark: Amsterdam
    state: absent

- name: Create one host per domain, all sharing the same settings
  kenyawest.remnawave.host:
    identify_by: address
    address: "{{ item }}"
    sni: "{{ item }}"
    state: enabled
    config_profile: default-profile
    inbound: vless-reality
    port: 443
    fingerprint: chrome
    nodes:
      - nl-ams-1
  loop: "{{ host_domains }}"

- name: Disable the hosts serving a list of domains
  kenyawest.remnawave.host:
    identify_by: address
    address: "{{ item }}"
    state: disabled
  loop: "{{ retired_domains }}"
'''

RETURN = r'''
host:
  description: The host object as returned by the Remnawave API (camelCase keys).
  type: dict
  returned: when state is not absent
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    STATE_CHOICES, FieldSpec, build_patch, desired_enabled, exit_with_change,
    remnawave_argument_spec, resolve_for_check_mode,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_host, resolve_inbound_uuids, resolve_node_uuids,
)


def build_fields(module, client):
    params = module.params
    fields = [
        FieldSpec('address', 'address'),
        FieldSpec('port', 'port'),
        FieldSpec('path', 'path', to_api=lambda v: v or None),
        FieldSpec('sni', 'sni', to_api=lambda v: v or None),
        FieldSpec('host_header', 'host', to_api=lambda v: v or None),
        FieldSpec('alpn', 'alpn'),
        FieldSpec('fingerprint', 'fingerprint', to_api=lambda v: v or None),
        FieldSpec('security_layer', 'securityLayer', to_api=lambda v: v.upper()),
        FieldSpec('hidden', 'isHidden'),
        FieldSpec('tags', 'tags', kind='set'),
        FieldSpec('server_description', 'serverDescription',
                  to_api=lambda v: v or None),
    ]
    resolved = dict(params)

    if params['identify_by'] != 'remark' and params['remark'] is not None:
        # Not the identifier here, so it is an ordinary field and may be
        # used to rename the host.
        fields.append(FieldSpec('remark', 'remark'))

    wanted_enabled = desired_enabled(params['state'])
    if wanted_enabled is not None:
        # state enabled/disabled is just the isDisabled field for a host.
        resolved['is_disabled'] = not wanted_enabled
        fields.append(FieldSpec('is_disabled', 'isDisabled'))

    if params['nodes'] is not None:
        resolved['nodes'] = resolve_for_check_mode(
            module,
            lambda: resolve_node_uuids(client, params['nodes']),
            list(params['nodes']))
        fields.append(FieldSpec('nodes', 'nodes', kind='set'))

    if params['config_profile'] is not None or params['inbound'] is not None:
        if params['config_profile'] is None or params['inbound'] is None:
            module.fail_json(
                msg='config_profile and inbound must be set together')
        profile_uuid, inbound_uuids = resolve_for_check_mode(
            module,
            lambda: resolve_inbound_uuids(
                client, params['config_profile'], [params['inbound']]),
            (params['config_profile'], [params['inbound']]))
        resolved['config_profile'] = {
            'configProfileUuid': profile_uuid,
            'configProfileInboundUuid': inbound_uuids[0],
        }
        fields.append(FieldSpec(
            'config_profile', 'inbound', kind='json',
            from_api=lambda v: {
                'configProfileUuid': (v or {}).get('configProfileUuid'),
                'configProfileInboundUuid': (v or {}).get('configProfileInboundUuid'),
            }))
    return fields, resolved


def run(module, client):
    params = module.params
    identify_by = params['identify_by']
    identifier = params[identify_by]
    if identifier is None:
        module.fail_json(
            msg='Option %s is required, because identify_by=%s makes it the '
                'identifier of the host' % (identify_by, identify_by))
    current = find_host(client, identifier, key=identify_by)

    if params['state'] == 'absent':
        if current is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            client.delete('/api/hosts/%s' % current['uuid'])
        exit_with_change(module, {identify_by: identifier}, {})

    fields, resolved = build_fields(module, client)
    patch, before, after = build_patch(resolved, current, fields)

    if current is None:
        missing = [opt for opt in ('config_profile', 'inbound', 'address', 'port')
                   if params[opt] is None]
        if missing:
            module.fail_json(
                msg='Creating host %r requires: %s'
                    % (identifier, ', '.join(missing)))
        payload = dict(patch)
        # The API always wants a remark; when hosts are addressed by domain
        # and no remark is given, the domain is the obvious display name.
        payload['remark'] = params['remark'] or params['address']
        if module.check_mode:
            exit_with_change(module, {},
                             dict(after, remark=payload['remark']), host=payload)
        created = client.post('/api/hosts', payload)
        exit_with_change(module, {},
                         dict(after, remark=payload['remark']), host=created)

    if not patch:
        module.exit_json(changed=False, host=current)

    payload = dict(patch)
    payload['uuid'] = current['uuid']
    if module.check_mode:
        exit_with_change(module, before, after, host=current)
    updated = client.patch('/api/hosts', payload)
    exit_with_change(module, before, after, host=updated)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        identify_by=dict(type='str', choices=['remark', 'address'],
                         default='remark'),
        remark=dict(type='str'),
        state=dict(type='str', choices=STATE_CHOICES, default='present'),
        nodes=dict(type='list', elements='str'),
        config_profile=dict(type='str'),
        inbound=dict(type='str'),
        address=dict(type='str'),
        port=dict(type='int'),
        path=dict(type='str'),
        sni=dict(type='str'),
        host_header=dict(type='str'),
        alpn=dict(type='str',
                  choices=['h3', 'h2', 'http/1.1', 'h2,http/1.1',
                           'h3,h2,http/1.1', 'h3,h2']),
        fingerprint=dict(type='str'),
        security_layer=dict(type='str', choices=['default', 'tls', 'none']),
        hidden=dict(type='bool'),
        tags=dict(type='list', elements='str'),
        server_description=dict(type='str'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[('identify_by', 'remark', ['remark']),
                     ('identify_by', 'address', ['address'])],
    )

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
