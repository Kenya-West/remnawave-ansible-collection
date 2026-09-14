#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: hosts
short_description: Manage many Remnawave subscription hosts in one task
version_added: 1.2.1
description:
  - Create, update, enable, disable and delete a list of hosts of a Remnawave
    panel in a declarative way, in a single task.
  - Every entry of O(hosts) takes the options of M(kenyawest.remnawave.host)
    and means the same thing. The difference is speed. A loop of
    M(kenyawest.remnawave.host) is one module run per host, and each run
    reads the panel's hosts, nodes, config profiles and squads again. This
    module reads each of them once for the whole list, then sends one
    request per host that needs a change and none for the rest.
  - Every entry is planned before anything is written. An entry that cannot
    be applied - an ambiguous or missing identifier, an unknown node, squad,
    config profile or inbound, a host missing what its creation requires -
    fails the task and nothing is changed.
  - Entries are planned against the panel as it is when the task starts. One
    entry therefore cannot rely on another entry's change, and a host may be
    declared only once; an entry addressing a host already declared by an
    earlier one fails the task.
  - Changes are applied in list order. If the panel rejects a write, the
    task fails at that entry; the entries before it stay applied and are
    reported in RV(results).
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
        diff per changed host.
    support: full
options:
  hosts:
    description:
      - The hosts to manage, each with the options of
        M(kenyawest.remnawave.host).
      - An empty list manages nothing. Hosts of the panel that are not listed
        are left alone.
    type: list
    elements: dict
    required: true
    suboptions:
      identify_by:
        description:
          - Which option identifies the host on the panel.
          - V(remark) (the default) searches by O(hosts[].remark), the host's
            display name.
          - V(address) searches by O(hosts[].address) instead. O(hosts[].remark)
            then becomes an ordinary managed field and may be used to rename
            the host.
          - The identifying option must match at most one host.
        type: str
        choices: [remark, address]
        default: remark
      remark:
        description:
          - Remark (display name) of the host.
          - Required and used as the identifier unless
            O(hosts[].identify_by=address). With O(hosts[].identify_by=address)
            it renames the host when set; omitted, a newly created host gets
            its address as its remark.
        type: str
      state:
        description:
          - V(present) ensures the host exists and leaves its enabled/disabled
            status alone.
          - V(enabled) and V(disabled) additionally ensure that status,
            creating the host first if needed.
          - V(absent) deletes the host.
        type: str
        choices: [present, absent, enabled, disabled]
        default: present
      nodes:
        description:
          - Nodes this host is bound to, by name or UUID. Authoritative when
            set; an empty list unbinds the host.
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
          - Required when the host does not exist yet, and always required
            with O(hosts[].identify_by=address), where it is the identifier.
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
          - Tags of the host. Authoritative when set; an empty list removes
            every tag.
          - At most 10 tags, each up to 36 characters of uppercase letters,
            digits, underscores and colons.
        type: list
        elements: str
      server_description:
        description:
          - Server description shown in some clients. Set to an empty string
            to clear it.
        type: str
      vless_route_id:
        description:
          - VLESS route id advertised with this host, an integer between 0 and
            65535. Set to an empty string to clear it.
        type: raw
      override_sni_from_address:
        description:
          - Whether the panel derives the SNI from O(hosts[].address) instead
            of using O(hosts[].sni).
        type: bool
      keep_sni_blank:
        description:
          - Whether to advertise an empty SNI rather than filling one in.
        type: bool
      exclude_from_subscription_types:
        description:
          - Subscription types this host is left out of. Authoritative when
            set; an empty list puts the host back into every subscription
            type.
        type: list
        elements: str
        choices: [XRAY_JSON, XRAY_BASE64, MIHOMO, STASH, CLASH, SINGBOX]
      internal_squads:
        description:
          - Which internal squads see this host. Both suboptions are required
            together, and the squad list is authoritative.
        type: dict
        suboptions:
          mode:
            description:
              - V(exclude) hides the host from the listed squads, V(allow_only)
                shows it to those squads alone.
            type: str
            choices: [exclude, allow_only]
            required: true
          squads:
            description:
              - Internal squads the mode applies to, by name or UUID. May be
                empty.
            type: list
            elements: str
            required: true
seealso:
  - module: kenyawest.remnawave.host
  - module: kenyawest.remnawave.host_info
'''

EXAMPLES = r'''
- name: Publish a host per exit and one per chain entry, in one task
  kenyawest.remnawave.hosts:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    hosts:
      - remark: Amsterdam
        state: enabled
        config_profile: default-profile
        inbound: vless-reality
        address: ams.example.com
        port: 443
        sni: ams.example.com
        nodes: [nl-ams-1]
      - remark: Amsterdam via Belgrade
        state: enabled
        config_profile: default-profile
        inbound: vless-reality
        address: chain-rs-1.example.com
        port: 443
        vless_route_id: 400
        override_sni_from_address: true

- name: Create one host per domain, all sharing the same settings
  kenyawest.remnawave.hosts:
    hosts: >-
      {{
        host_domains | map('community.general.dict_kv', 'address')
        | map('combine', {'identify_by': 'address', 'state': 'enabled',
                          'config_profile': 'default-profile',
                          'inbound': 'vless-reality', 'port': 443})
        | list
      }}

- name: Retire hosts by remark
  kenyawest.remnawave.hosts:
    hosts: "{{ retired_remarks | map('community.general.dict_kv', 'remark')
               | map('combine', {'state': 'absent'}) | list }}"
  register: retired

- name: Report the hosts that were actually deleted
  ansible.builtin.debug:
    msg: "{{ retired.results | selectattr('changed') | map(attribute='identifier') | list }}"
'''

RETURN = r'''
results:
  description:
    - One item per entry of O(hosts), in the same order.
  type: list
  elements: dict
  returned: always
  contains:
    identify_by:
      description: Which option identified the host, V(remark) or V(address).
      type: str
      returned: always
    identifier:
      description: The value of that option.
      type: str
      returned: always
    action:
      description:
        - What was (or, in check mode, would be) done to the host -
          V(create), V(update), V(delete) or V(none).
        - Enabling and disabling a host is an V(update).
      type: str
      returned: always
    changed:
      description: Whether this host changed.
      type: bool
      returned: always
    host:
      description:
        - The host object as returned by the Remnawave API (camelCase keys).
        - In check mode, the host as found, or the payload that would create
          it.
      type: dict
      returned: unless the host is, or would be, absent
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.host import (
    HOST_REQUIRED_IF, apply_host_plan, host_options, plan_hosts,
)


def run(module, client):
    try:
        plans = plan_hosts(module, client, module.params['hosts'])
    except RemnawaveApiError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc,
                         status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg='%s. Nothing was changed.' % exc)

    results = []
    diffs = []
    for plan in plans:
        try:
            result = apply_host_plan(module, client, plan)
        except RemnawaveApiError as exc:
            module.fail_json(
                msg='%s: %s' % (plan['label'], exc),
                status=exc.status, error_code=exc.error_code,
                changed=any(r['changed'] for r in results), results=results)
        diff = result.pop('diff', None)
        if diff is not None:
            diffs.append(dict(diff, before_header=plan['label'],
                              after_header=plan['label']))
        result.update(identify_by=plan['identify_by'],
                      identifier=plan['identifier'], action=plan['action'])
        results.append(result)

    output = dict(changed=any(r['changed'] for r in results), results=results)
    if diffs:
        output['diff'] = diffs
    module.exit_json(**output)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        hosts=dict(type='list', elements='dict', required=True,
                   options=host_options(), required_if=HOST_REQUIRED_IF),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    run(module, client)


if __name__ == '__main__':
    main()
