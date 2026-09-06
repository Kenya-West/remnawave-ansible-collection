#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: snippet
short_description: Manage Remnawave snippets
description:
  - Create, update and delete snippets (reusable configuration fragments)
    of a Remnawave panel in a declarative way.
  - Snippets are identified by their C(name), which is also how the API
    addresses them - they have no UUID.
  - The supplied O(snippet) is treated as authoritative - the stored content
    is made exactly equal to it.
  - Changing a snippet does not by itself reach the config profiles that
    embed it; the panel has a separate sync action for that, which this
    module runs for you whenever it changed something. See O(sync).
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
      - Name of the snippet, and the identifier the module searches by.
      - The panel restricts names to letters, digits, spaces, underscores
        and hyphens, and allows C(/) to group them into folders, for example
        V(outbounds/warp). It cannot be changed through this module; a
        renamed snippet is a new one.
    type: str
    required: true
  state:
    description:
      - Whether the snippet should exist.
    type: str
    choices: [present, absent]
    default: present
  snippet:
    description:
      - Content of the snippet - a list of configuration objects, or a
        JSON-encoded string holding that list.
      - Required when the snippet does not exist yet.
    type: raw
  sync:
    description:
      - Whether to push the snippet into the config profiles that embed it,
        using the panel's sync action.
      - V(on_change) syncs only when this task created or updated the
        snippet, which leaves a converged run untouched.
      - V(never) skips syncing, for example when you update several snippets
        and want to sync them yourself afterwards.
      - V(always) syncs on every run, even when the content already matched.
        This is an action rather than a state, so such a task always reports
        C(changed); use it deliberately, for instance to repair profiles
        that drifted.
      - Deleting a snippet never syncs, because there is nothing left to
        push.
    type: str
    choices: [on_change, never, always]
    default: on_change
seealso:
  - module: kenyawest.remnawave.snippet_info
  - module: kenyawest.remnawave.config_profile
'''

EXAMPLES = r'''
- name: Ensure a snippet matches the file in the repository
  kenyawest.remnawave.snippet:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: outbounds/warp
    state: present
    snippet: "{{ lookup('ansible.builtin.file', 'files/warp-outbound.json') }}"

- name: Define a snippet inline
  kenyawest.remnawave.snippet:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: dns-block
    snippet:
      - tag: block
        protocol: blackhole

- name: Update several snippets, then sync them once
  block:
    - kenyawest.remnawave.snippet:
        name: "{{ item.name }}"
        snippet: "{{ item.snippet }}"
        sync: never
      loop: "{{ remnawave_snippet_batch }}"
      register: batch

    - kenyawest.remnawave.snippet:
        name: "{{ item.item.name }}"
        sync: always
      loop: "{{ batch.results | selectattr('changed') | list }}"

- name: Remove a snippet
  kenyawest.remnawave.snippet:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    name: legacy-fragment
    state: absent
'''

RETURN = r'''
snippet:
  description:
    - The snippet as returned by the Remnawave API, with its C(name) and its
      C(snippet) content.
  type: dict
  returned: when state=present
synced:
  description:
    - Whether the sync action was run against the config profiles embedding
      this snippet.
  type: bool
  returned: always
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    exit_with_change, parse_json_option, remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    create_snippet, find_snippet, sync_snippet, update_snippet,
)


def maybe_sync(module, client, name, changed):
    """Run the sync action if the sync option calls for it."""
    sync = module.params['sync']
    if sync == 'never' or (sync == 'on_change' and not changed):
        return False
    if not module.check_mode:
        sync_snippet(client, name)
    return True


def run(module, client):
    params = module.params
    name = params['name']
    current = find_snippet(client, name)

    if params['state'] == 'absent':
        # Nothing to push into the profiles once the snippet is gone.
        if current is None:
            module.exit_json(changed=False, synced=False)
        if not module.check_mode:
            client.delete('/api/snippets', {'name': name})
        exit_with_change(module, {'name': name}, {}, synced=False)

    content = parse_json_option(params['snippet'], 'snippet', module)

    if current is None:
        if content is None:
            module.fail_json(
                msg='snippet is required when creating snippet %r' % name)
        payload = {'name': name, 'snippet': content}
        if module.check_mode:
            synced = maybe_sync(module, client, name, True)
            exit_with_change(module, {}, payload, snippet=payload, synced=synced)
        created = create_snippet(client, name, content)
        synced = maybe_sync(module, client, name, True)
        exit_with_change(module, {}, payload, snippet=created, synced=synced)

    if content is None or content == current.get('snippet'):
        synced = maybe_sync(module, client, name, False)
        if not synced:
            module.exit_json(changed=False, snippet=current, synced=False)
        # sync=always performed an action, so the task did do something.
        module.exit_json(changed=True, snippet=current, synced=True)

    before = {'snippet': current.get('snippet')}
    after = {'snippet': content}
    if module.check_mode:
        synced = maybe_sync(module, client, name, True)
        exit_with_change(module, before, after, snippet=current, synced=synced)
    updated = update_snippet(client, name, content)
    synced = maybe_sync(module, client, name, True)
    exit_with_change(module, before, after, snippet=updated, synced=synced)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        snippet=dict(type='raw'),
        sync=dict(type='str', choices=['on_change', 'never', 'always'],
                  default='on_change'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
