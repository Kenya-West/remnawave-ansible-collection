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
  - The inbound is referenced by its tag and resolved to UUIDs
    automatically, along with the config profile holding it. Inbound tags
    are unique across profiles, so naming the profile is optional.
  - Advanced host properties not covered by this module (mux, sockopt,
    mappers, subscription mappers and so on) can be managed with
    M(kenyawest.remnawave.api).
  - To manage many hosts, prefer M(kenyawest.remnawave.hosts) over a loop
    of this module. It reads the panel once for all of them, where every
    loop iteration is a module run of its own.
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
      - Optional, since it is the profile holding O(inbound). Set, the
        inbound must belong to it. Requires O(inbound).
    type: str
  inbound:
    description:
      - Inbound the host serves, by tag or UUID.
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
      - Tags of the host. Authoritative when set; an empty list removes
        every tag.
      - At most 10 tags, each up to 36 characters of uppercase letters,
        digits, underscores and colons.
    type: list
    elements: str
  server_description:
    description:
      - Server description shown in some clients. Set to an empty string to
        clear it.
    type: str
  vless_route_id:
    description:
      - VLESS route id advertised with this host, which the routing rules of
        a config profile match on to send the host's traffic through a
        particular outbound or balancer.
      - An integer between 0 and 65535. Set to an empty string to clear it,
        which leaves the host with no route id.
    type: raw
  override_sni_from_address:
    description:
      - Whether the panel derives the SNI from O(address) instead of using
        O(sni) - what chain entries normally want, since the address they
        publish is not the domain the exit node terminates TLS for.
    type: bool
  keep_sni_blank:
    description:
      - Whether to advertise an empty SNI rather than filling one in.
    type: bool
  exclude_from_subscription_types:
    description:
      - Subscription types this host is left out of. Authoritative when set;
        an empty list puts the host back into every subscription type.
    type: list
    elements: str
    choices: [XRAY_JSON, XRAY_BASE64, MIHOMO, STASH, CLASH, SINGBOX]
  internal_squads:
    description:
      - Which internal squads see this host.
      - Both suboptions are required together, and the squad list is
        authoritative.
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
  - module: kenyawest.remnawave.hosts
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

- name: Publish a chain entry that routes to one exit by its VLESS route id
  kenyawest.remnawave.host:
    remark: Amsterdam via Belgrade
    state: enabled
    config_profile: default-profile
    inbound: vless-reality
    address: chain-rs-1.example.com
    port: 443
    vless_route_id: 400
    override_sni_from_address: true
    exclude_from_subscription_types:
      - SINGBOX
    internal_squads:
      mode: exclude
      squads:
        - trial-squad

- name: Take a host's route id away again
  kenyawest.remnawave.host:
    remark: Amsterdam via Belgrade
    vless_route_id: ""
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
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.host import (
    HOST_REQUIRED_IF, apply_host_plan, host_options, plan_host,
)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(host_options())
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=HOST_REQUIRED_IF,
    )

    client = RemnawaveClient(module)
    try:
        plan = plan_host(module, client, module.params)
        module.exit_json(**apply_host_plan(module, client, plan))
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)
    except ValueError as exc:
        module.fail_json(msg=str(exc))


if __name__ == '__main__':
    main()
