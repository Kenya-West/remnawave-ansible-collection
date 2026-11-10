#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: internal_squad
short_description: Manage Remnawave internal squads
description:
  - Create, update and delete internal squads of a Remnawave panel in a
    declarative way.
  - Squads are identified by their C(name).
  - Inbounds are referenced by tag, optionally together with their config
    profile, or by UUID, and resolved automatically. The list is
    authoritative when set.
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
      - Name of the internal squad. This is the stable identifier the module
        searches by; it cannot be changed through this module.
    type: str
    required: true
  state:
    description:
      - Whether the squad should exist.
    type: str
    choices: [present, absent]
    default: present
  inbounds:
    description:
      - Inbounds that belong to the squad.
      - Each item is an inbound tag or UUID as a plain string, or a dict with
        C(tag) (inbound tag or UUID) and optionally C(profile) (config profile
        name or UUID), which the inbound must then belong to.
      - Inbound tags are unique across config profiles, so the plain tag is
        enough; the dict form is kept for playbooks written before plain tags
        were accepted.
      - Required when the squad does not exist yet.
    type: list
    elements: raw
  tags:
    description:
      - Tags of the squad. Authoritative when set; an empty list removes
        every tag.
      - At most 10 tags, each up to 36 characters of uppercase letters,
        digits, underscores and colons.
      - Not to be confused with the inbound C(tag) inside O(inbounds).
    type: list
    elements: str
    version_added: 1.2.0
seealso:
  - module: kenyawest.remnawave.internal_squad_info
  - module: kenyawest.remnawave.user
'''

EXAMPLES = r'''
- name: Ensure internal squad exists
  kenyawest.remnawave.internal_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: default-squad
    state: present
    inbounds:
      - vless-reality
      - ss-inbound
    tags:
      - PAID

- name: The same, naming the config profile of an inbound as well
  kenyawest.remnawave.internal_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: default-squad
    inbounds:
      - profile: default-profile
        tag: vless-reality
      - ss-inbound

- name: Remove a squad
  kenyawest.remnawave.internal_squad:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: old-squad
    state: absent
'''

RETURN = r'''
squad:
  description: The internal squad as returned by the Remnawave API.
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
from ansible_collections.kenyawest.remnawave.plugins.module_utils.squad import (
    entity_options, run_single,
)


def run(module, client):
    run_single(module, client, 'internal_squad')


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(entity_options('internal_squad'))
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
