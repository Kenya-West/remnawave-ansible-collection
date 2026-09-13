#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: user_info
short_description: Retrieve Remnawave users
description:
  - Retrieve one user by username, id or short UUID, or list the users of a
    Remnawave panel, optionally filtered, sorted and paginated.
  - The panel offers two listing endpoints with different query parameters,
    and the options used decide which one is called. O(status),
    O(traffic_limit_strategy), O(telegram_id), O(email), O(tag),
    O(external_squad) and O(cursor) use the cursor-paginated stream
    endpoint. O(filters), O(filter_modes), O(global_filter_mode), O(sorting)
    and O(start) use the offset-paginated table endpoint. The two groups
    cannot be combined.
  - Without O(size), O(start) or O(cursor) every page is fetched and all
    matching users are returned. With any of them, a single page is returned
    together with the pagination details needed to fetch the next one.
  - This module never changes anything and always returns C(changed=false).
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
    support: none
options:
  username:
    description:
      - Return only the user with this username.
      - Mutually exclusive with O(id), O(short_uuid) and the listing options.
    type: str
  id:
    description:
      - Return only the user with this numeric id.
      - Mutually exclusive with O(username), O(short_uuid) and the listing
        options.
    type: int
    version_added: 1.2.0
  short_uuid:
    description:
      - Return only the user with this short UUID, the identifier used in
        subscription URLs.
      - Mutually exclusive with O(username), O(id) and the listing options.
    type: str
    version_added: 1.2.0
  status:
    description:
      - Return only users with this status. Stream endpoint.
    type: str
    choices: [active, disabled, limited, expired]
    version_added: 1.2.0
  traffic_limit_strategy:
    description:
      - Return only users with this traffic reset strategy. Stream endpoint.
    type: str
    choices: [no_reset, day, week, month, month_rolling]
    version_added: 1.2.0
  telegram_id:
    description:
      - Return only users with this Telegram id. Stream endpoint.
    type: int
    version_added: 1.2.0
  email:
    description:
      - Return only users with this e-mail address. Stream endpoint.
    type: str
    version_added: 1.2.0
  tag:
    description:
      - Return only users with this tag. Stream endpoint.
    type: str
    version_added: 1.2.0
  external_squad:
    description:
      - Return only users in this external squad, by name or UUID. Stream
        endpoint.
    type: str
    version_added: 1.2.0
  cursor:
    description:
      - Fetch the single stream page that starts at this cursor, as returned
        in RV(next_cursor) by a previous call. Stream endpoint.
    type: str
    version_added: 1.2.0
  filters:
    description:
      - Column filters of the table endpoint, sent to the panel as JSON.
      - The panel notes that these rely on expensive operators such as
        C(LIKE); prefer the stream filters where they suffice.
    type: list
    elements: dict
    version_added: 1.2.0
    suboptions:
      id:
        description:
          - The user field to filter on, for example V(username).
        type: str
        required: true
      value:
        description:
          - The value to filter by.
        type: raw
        required: true
  filter_modes:
    description:
      - Filter mode per field of O(filters), keyed by field, for example
        V(contains) for key V(username). Table endpoint.
    type: dict
    version_added: 1.2.0
  global_filter_mode:
    description:
      - Global filter mode of the table endpoint.
    type: str
    version_added: 1.2.0
  sorting:
    description:
      - Sort order of the table endpoint, most significant first.
    type: list
    elements: dict
    version_added: 1.2.0
    suboptions:
      id:
        description:
          - The user field to sort by, for example V(createdAt).
        type: str
        required: true
      desc:
        description:
          - Whether to sort in descending order.
        type: bool
        default: false
  start:
    description:
      - Offset of the single table page to fetch.
    type: int
    version_added: 1.2.0
  size:
    description:
      - Number of users in the single page to fetch, at most 1000.
      - Works with either endpoint; on its own it selects the table endpoint.
    type: int
    version_added: 1.2.0
seealso:
  - module: kenyawest.remnawave.user
'''

EXAMPLES = r'''
- name: Get a single user
  kenyawest.remnawave.user_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    username: alice
  register: result

- name: List all users
  kenyawest.remnawave.user_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
  register: result

- name: All disabled users of the resellers squad
  kenyawest.remnawave.user_info:
    status: disabled
    external_squad: resellers
  register: result

- name: First page of users whose name contains "test", newest first
  kenyawest.remnawave.user_info:
    filters:
      - id: username
        value: test
    filter_modes:
      username: contains
    sorting:
      - id: createdAt
        desc: true
    size: 50
  register: page
'''

RETURN = r'''
users:
  description:
    - Matching users as returned by the Remnawave API (camelCase keys).
    - Empty list when a requested user does not exist.
  type: list
  elements: dict
  returned: always
total:
  description: Number of users matching the table endpoint's filters.
  type: int
  returned: when a single page of the table endpoint was fetched
next_cursor:
  description:
    - Cursor of the next stream page, to pass as O(cursor), or V(null) on
      the last page.
  type: str
  returned: when a single page of the stream endpoint was fetched
has_more:
  description: Whether the stream has further pages.
  type: bool
  returned: when a single page of the stream endpoint was fetched
'''

import json

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_external_squad, get_user_by_username,
)

PAGE_SIZE = 500
LOOKUP_OPTIONS = ('username', 'id', 'short_uuid')
STREAM_OPTIONS = ('status', 'traffic_limit_strategy', 'telegram_id', 'email',
                  'tag', 'external_squad', 'cursor')
TABLE_OPTIONS = ('filters', 'filter_modes', 'global_filter_mode', 'sorting',
                 'start')


def table_query(module, start, size):
    """Query of the offset-paginated /api/users endpoint.

    The panel parses filters, filterModes and sorting out of JSON strings.
    """
    params = module.params
    query = {'start': start, 'size': size,
             'globalFilterMode': params['global_filter_mode']}
    if params['filters'] is not None:
        query['filters'] = json.dumps(params['filters'])
    if params['filter_modes'] is not None:
        query['filterModes'] = json.dumps(params['filter_modes'])
    if params['sorting'] is not None:
        query['sorting'] = json.dumps(params['sorting'])
    return query


def list_table(module, client):
    params = module.params
    if params['start'] is not None or params['size'] is not None:
        data = client.get('/api/users', query=table_query(
            module, params['start'] or 0, params['size'] or PAGE_SIZE)) or {}
        return dict(users=data.get('users', []), total=data.get('total'))

    users = []
    start = 0
    while True:
        data = client.get('/api/users',
                          query=table_query(module, start, PAGE_SIZE)) or {}
        page = data.get('users', [])
        users.extend(page)
        total = data.get('total', len(users))
        start += PAGE_SIZE
        if not page or len(users) >= total:
            return dict(users=users)


def stream_query(module, client):
    params = module.params
    query = {
        'status': params['status'] and params['status'].upper(),
        'trafficLimitStrategy': (params['traffic_limit_strategy']
                                 and params['traffic_limit_strategy'].upper()),
        'telegramId': params['telegram_id'],
        'email': params['email'],
        'tag': params['tag'],
    }
    if params['external_squad'] is not None:
        squad = find_external_squad(client, params['external_squad'],
                                    required=True)
        query['externalSquadUuid'] = squad['uuid']
    return query


def list_stream(module, client):
    params = module.params
    query = stream_query(module, client)
    if params['cursor'] is not None or params['size'] is not None:
        query.update(cursor=params['cursor'], size=params['size'] or PAGE_SIZE)
        data = client.get('/api/users/stream', query=query) or {}
        return dict(users=data.get('users', []),
                    next_cursor=data.get('nextCursor'),
                    has_more=bool(data.get('hasMore')))

    users = []
    cursor = None
    while True:
        query.update(cursor=cursor, size=PAGE_SIZE)
        data = client.get('/api/users/stream', query=query) or {}
        users.extend(data.get('users', []))
        cursor = data.get('nextCursor')
        if not data.get('hasMore') or cursor is None:
            return dict(users=users)


def run(module, client):
    params = module.params
    if params['username'] is not None:
        user = get_user_by_username(client, params['username'])
        return dict(users=[user] if user is not None else [])
    if params['id'] is not None:
        user = client.get('/api/users/%d' % params['id'], allow_404=True)
        return dict(users=[user] if user is not None else [])
    if params['short_uuid'] is not None:
        user = client.get('/api/users/by-short-uuid/%s' % params['short_uuid'],
                          allow_404=True)
        return dict(users=[user] if user is not None else [])

    stream = [o for o in STREAM_OPTIONS if params[o] is not None]
    table = [o for o in TABLE_OPTIONS if params[o] is not None]
    if stream and table:
        module.fail_json(
            msg='Stream endpoint options (%s) and table endpoint options (%s) '
                'cannot be combined'
                % (', '.join(stream), ', '.join(table)))
    if params['size'] is not None and not 1 <= params['size'] <= 1000:
        module.fail_json(msg='size must be between 1 and 1000, got %d'
                             % params['size'])
    if stream:
        return list_stream(module, client)
    return list_table(module, client)


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        username=dict(type='str'),
        id=dict(type='int'),
        short_uuid=dict(type='str'),
        status=dict(type='str',
                    choices=['active', 'disabled', 'limited', 'expired']),
        traffic_limit_strategy=dict(
            type='str',
            choices=['no_reset', 'day', 'week', 'month', 'month_rolling']),
        telegram_id=dict(type='int'),
        email=dict(type='str'),
        tag=dict(type='str'),
        external_squad=dict(type='str'),
        cursor=dict(type='str'),
        filters=dict(type='list', elements='dict', options=dict(
            id=dict(type='str', required=True),
            value=dict(type='raw', required=True),
        )),
        filter_modes=dict(type='dict'),
        global_filter_mode=dict(type='str'),
        sorting=dict(type='list', elements='dict', options=dict(
            id=dict(type='str', required=True),
            desc=dict(type='bool', default=False),
        )),
        start=dict(type='int'),
        size=dict(type='int'),
    )
    listing = STREAM_OPTIONS + TABLE_OPTIONS + ('size',)
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[LOOKUP_OPTIONS] + [
            (lookup, option) for lookup in LOOKUP_OPTIONS for option in listing],
    )

    client = RemnawaveClient(module)
    try:
        module.exit_json(changed=False, **run(module, client))
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
