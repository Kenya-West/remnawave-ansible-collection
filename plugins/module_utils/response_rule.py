# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Named rules within the subscription-settings singleton.

Rules have no endpoint or UUID of their own. Updating one preserves every
other rule, the evaluation order, and the response-rule configuration settings.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from copy import deepcopy
import re

from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    FieldSpec, build_patch, desired_enabled, parse_json_option,
)

HEADER_RE = re.compile(r"^[!#$%&'*+\-.0-9A-Z^_`a-z|~]+$")

RESPONSE_TYPES = ['XRAY_JSON', 'XRAY_BASE64', 'MIHOMO', 'STASH', 'CLASH',
                  'SINGBOX', 'BROWSER', 'BLOCK', 'STATUS_CODE_404',
                  'STATUS_CODE_451', 'SOCKET_DROP']
CONDITION_OPERATORS = ['EQUALS', 'NOT_EQUALS', 'CONTAINS', 'NOT_CONTAINS',
                       'STARTS_WITH', 'NOT_STARTS_WITH', 'ENDS_WITH',
                       'NOT_ENDS_WITH', 'REGEX', 'NOT_REGEX']
FIELDS = [FieldSpec('description', 'description'), FieldSpec('operator', 'operator'),
          FieldSpec('conditions', 'conditions', kind='list'),
          FieldSpec('response_type', 'responseType'),
          FieldSpec('response_modifications', 'responseModifications', kind='json')]


def response_rule_options():
    return dict(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent', 'enabled', 'disabled'], default='present'),
        description=dict(type='str'), operator=dict(type='str', choices=['AND', 'OR']),
        conditions=dict(type='list', elements='dict', options=dict(
            header_name=dict(type='str', required=True),
            operator=dict(type='str', choices=CONDITION_OPERATORS, required=True),
            value=dict(type='str', required=True), case_sensitive=dict(type='bool', default=False))),
        response_type=dict(type='str', choices=RESPONSE_TYPES),
        response_modifications=dict(type='raw'),
    )


def plan_response_rules(module, current, entries, order=False):
    config = deepcopy(current.get('responseRules') or {'version': '1', 'rules': []})
    if config.get('version') != '1' or not isinstance(config.get('rules'), list):
        raise ValueError('Unsupported response rule configuration; expected version 1 and a rules list')
    original = deepcopy(config)
    rules = config['rules']
    names = [r['name'] for r in rules]
    if len(names) != len(set(names)):
        raise ValueError('Multiple response rules share a name; names must be unambiguous')
    claimed, results = set(), []
    for index, params in enumerate(entries):
        name = params['name']
        label = 'rules[%d] (%r)' % (index, name)
        if name in claimed:
            raise ValueError('%s is declared twice' % label)
        claimed.add(name)
        found = next((r for r in rules if r['name'] == name), None)
        result = dict(name=name, action='none', changed=False)
        before, after = {}, {}
        if params['state'] == 'absent':
            if found is not None:
                rules.remove(found)
                result.update(action='delete', changed=True)
                before = found
        else:
            if not 1 <= len(name) <= 50:
                raise ValueError('%s: name must be 1 to 50 characters long' % label)
            resolved = dict(params)
            if params.get('description') is not None and not 1 <= len(params['description']) <= 250:
                raise ValueError('%s: description must be 1 to 250 characters long' % label)
            if params.get('conditions') is not None:
                for condition in params['conditions']:
                    if not HEADER_RE.match(condition['header_name']):
                        raise ValueError('%s: invalid HTTP header name %r'
                                         % (label, condition['header_name']))
                    if not 1 <= len(condition['value']) <= 255:
                        raise ValueError('%s: condition value must be 1 to 255 characters long' % label)
                resolved['conditions'] = [dict(headerName=c['header_name'], operator=c['operator'],
                                               value=c['value'], caseSensitive=c['case_sensitive'])
                                          for c in params['conditions']]
            if params.get('response_modifications') is not None:
                resolved['response_modifications'] = parse_json_option(
                    params['response_modifications'], 'response_modifications', module)
                if not isinstance(resolved['response_modifications'], dict):
                    raise ValueError('%s: response_modifications must be a dict' % label)
            patch, before, after = build_patch(resolved, found, FIELDS)
            enabled = desired_enabled(params['state'])
            if found is None:
                if params.get('response_type') is None:
                    raise ValueError('%s: response_type is required when creating a rule' % label)
                rule = dict(name=name, enabled=enabled if enabled is not None else True,
                            operator='AND', conditions=[])
                rule.update(patch)
                rules.append(rule)
                after, before = deepcopy(rule), {}
                result.update(action='create', changed=True)
            else:
                rule = found
                if enabled is not None and enabled != rule['enabled']:
                    patch['enabled'], before['enabled'], after['enabled'] = enabled, rule['enabled'], enabled
                if patch:
                    rule.update(patch)
                    result.update(action='update', changed=True)
            result['rule'] = deepcopy(rule)
        if result['changed'] and module._diff:
            result['diff'] = dict(before=before, after=after,
                                  before_header=label, after_header=label)
        results.append(result)
    if order:
        kept = [p['name'] for p in entries if p['state'] != 'absent']
        slots = [i for i, r in enumerate(rules) if r['name'] in kept]
        by_name = dict((r['name'], r) for r in rules)
        prior = [r['name'] for r in rules]
        for slot, name in zip(slots, kept):
            rules[slot] = by_name[name]
        positions = dict((r['name'], i) for i, r in enumerate(rules))
        for result in results:
            name = result['name']
            if name not in positions or name not in prior:
                continue
            old, new = prior.index(name), positions[name]
            if old != new:
                result['changed'] = True
                if result['action'] == 'none':
                    result['action'] = 'update'
                if module._diff:
                    diff = result.setdefault('diff', dict(before={}, after={}))
                    diff['before']['position'], diff['after']['position'] = old, new
    return config, results, config != original


def run_response_rules(module, client, batch=False):
    current = client.get('/api/subscription-settings')
    entries = module.params['rules'] if batch else [module.params]
    config, results, changed = plan_response_rules(module, current, entries,
                                                   module.params.get('order', False))
    if changed and not module.check_mode:
        client.patch('/api/subscription-settings', {'uuid': current['uuid'], 'responseRules': config})
    if batch:
        diffs = [r.pop('diff') for r in results if 'diff' in r]
        kwargs = dict(changed=changed, results=results)
        if diffs:
            kwargs['diff'] = diffs
    else:
        kwargs = results[0]
        kwargs.pop('name')
        kwargs.pop('action')
    module.exit_json(**kwargs)
