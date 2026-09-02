#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: api
short_description: Call an arbitrary Remnawave API endpoint
description:
  - Low-level escape hatch for Remnawave API functionality that the resource
    modules of this collection do not model.
  - Prefer the resource modules such as M(kenyawest.remnawave.user) and
    M(kenyawest.remnawave.node) whenever they cover your use case; this
    module knows nothing about desired state and cannot be idempotent on its
    own. Combine it with C(changed_when) and C(when) as appropriate.
author: Kenya-West (@Kenya-West)
extends_documentation_fragment:
  - kenyawest.remnawave.remnawave
attributes:
  check_mode:
    description:
      - Can run in C(check_mode) and predict changes without modifying the panel.
    support: partial
    details:
      - GET requests are performed in check mode; other methods are skipped.
  diff_mode:
    description:
      - Returns what changed (or would change) when run with C(--diff).
    support: none
options:
  path:
    description:
      - API path starting with C(/api).
    type: str
    required: true
  method:
    description:
      - HTTP method.
    type: str
    choices: [GET, POST, PATCH, PUT, DELETE]
    default: GET
  body:
    description:
      - Request body, as a dict/list or JSON-encoded string.
    type: raw
  query:
    description:
      - Query string parameters.
    type: dict
  status_codes:
    description:
      - HTTP status codes considered a success.
      - By default any 2xx status is a success.
    type: list
    elements: int
'''

EXAMPLES = r'''
- name: Reset traffic of a user (intentionally non-idempotent action)
  kenyawest.remnawave.api:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    method: POST
    path: "/api/users/{{ user_id }}/actions/reset-traffic"

- name: Read panel health
  kenyawest.remnawave.api:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    path: /api/system/health
  register: health
'''

RETURN = r'''
status:
  description: HTTP status code of the response.
  type: int
  returned: always
response:
  description:
    - Parsed JSON body of the response, with Remnawave's C(response)
      envelope unwrapped.
  type: raw
  returned: always
skipped:
  description: True when a write request was skipped because of check mode.
  type: bool
  returned: in check mode
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    parse_json_option, remnawave_argument_spec,
)


def run(module, client):
    params = module.params
    method = params['method']
    body = parse_json_option(params['body'], 'body', module)

    if module.check_mode and method != 'GET':
        module.exit_json(changed=True, skipped=True, status=None, response=None)

    status, parsed = client.request(
        method, params['path'], query=params['query'], data=body,
        ok_statuses=tuple(params['status_codes'] or ()))
    if params['status_codes'] and status not in params['status_codes']:
        module.fail_json(
            msg='Unexpected HTTP status %s (expected one of %s)'
                % (status, params['status_codes']),
            status=status, response=parsed)
    module.exit_json(
        changed=(method != 'GET'), status=status,
        response=RemnawaveClient._unwrap(parsed))


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        path=dict(type='str', required=True),
        method=dict(type='str', default='GET',
                    choices=['GET', 'POST', 'PATCH', 'PUT', 'DELETE']),
        body=dict(type='raw'),
        query=dict(type='dict'),
        status_codes=dict(type='list', elements='int'),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    try:
        run(module, client)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
