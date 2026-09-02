#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: system_info
short_description: Retrieve Remnawave system information
description:
  - Retrieve health, statistics and metadata of a Remnawave panel.
  - This module never changes anything and always returns C(changed=false).
  - Useful as a connectivity/credential check at the start of a play.
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
  gather:
    description:
      - Which subjects to gather.
    type: list
    elements: str
    choices: [health, stats, bandwidth, nodes_statistics, metadata]
    default: [health]
'''

EXAMPLES = r'''
- name: Verify the panel is reachable and the token works
  kenyawest.remnawave.system_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"

- name: Gather panel statistics
  kenyawest.remnawave.system_info:
    panel_url: https://panel.example.com
    token: "{{ remnawave_token }}"
    gather: [health, stats, bandwidth]
  register: system
'''

RETURN = r'''
health:
  description: Panel health information.
  type: dict
  returned: when V(health) is gathered
stats:
  description: Panel statistics.
  type: dict
  returned: when V(stats) is gathered
bandwidth:
  description: Bandwidth statistics.
  type: dict
  returned: when V(bandwidth) is gathered
nodes_statistics:
  description: Per-node statistics.
  type: dict
  returned: when V(nodes_statistics) is gathered
metadata:
  description: Panel metadata.
  type: dict
  returned: when V(metadata) is gathered
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    remnawave_argument_spec,
)

PATHS = {
    'health': '/api/system/health',
    'stats': '/api/system/stats',
    'bandwidth': '/api/system/stats/bandwidth',
    'nodes_statistics': '/api/system/stats/nodes',
    'metadata': '/api/system/metadata',
}


def main():
    argument_spec = remnawave_argument_spec()
    argument_spec.update(
        gather=dict(type='list', elements='str', default=['health'],
                    choices=sorted(PATHS)),
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    client = RemnawaveClient(module)
    result = dict(changed=False)
    try:
        for subject in module.params['gather']:
            result[subject] = client.get(PATHS[subject])
        module.exit_json(**result)
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code)


if __name__ == '__main__':
    main()
