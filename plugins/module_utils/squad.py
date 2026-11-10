# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Shared planning and applying for squads and subscription templates."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import base64

from ansible_collections.kenyawest.remnawave.plugins.module_utils.batch import (
    DEFAULT_PARALLELISM, arrange, collect_outcomes,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import RemnawaveApiError
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    FieldSpec, build_patch, is_uuid, parse_json_option, resolve_for_check_mode,
    tags_differ, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_external_squad, find_internal_squad, find_subscription_template,
    list_external_squads, list_internal_squads, list_subscription_templates,
    resolve_inbound_uuids, set_tags,
)

TEMPLATE_TYPES = ['XRAY_JSON', 'XRAY_BASE64', 'MIHOMO', 'STASH', 'CLASH', 'SINGBOX']
RESOURCES = {
    'internal_squad': ('internal-squads', 'squads', 'squad',
                       list_internal_squads, find_internal_squad, 30),
    'external_squad': ('external-squads', 'squads', 'squad',
                       list_external_squads, find_external_squad, 30),
    'subscription_template': ('subscription-templates', 'templates', 'template',
                              list_subscription_templates, find_subscription_template, 255),
}
EXTERNAL_FIELDS = [
    FieldSpec('templates', 'templates', kind='json',
              from_api=lambda v: sorted(v or [], key=lambda t: t['templateType'])),
    FieldSpec('subscription_settings', 'subscriptionSettings', kind='json',
              from_api=lambda v: v or {}),
    FieldSpec('host_overrides', 'hostOverrides', kind='json',
              from_api=lambda v: v or {}),
    FieldSpec('response_headers_add', 'responseHeadersAdd', kind='json',
              from_api=lambda v: v or {}),
    FieldSpec('response_headers_remove', 'responseHeadersRemove', kind='set',
              from_api=lambda v: v or []),
    FieldSpec('hwid_settings', 'hwidSettings', kind='json'),
    FieldSpec('custom_remarks', 'customRemarks', kind='json'),
    FieldSpec('subpage_config_uuid', 'subpageConfigUuid', to_api=lambda v: v or None),
]


def entity_options(kind):
    options = dict(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        tags=dict(type='list', elements='str'),
    )
    if kind == 'internal_squad':
        options['inbounds'] = dict(type='list', elements='raw')
    elif kind == 'subscription_template':
        options.update(template_type=dict(type='str', choices=TEMPLATE_TYPES),
                       template_json=dict(type='raw'), template_yaml=dict(type='str'))
    else:
        options.update(
            templates=dict(type='list', elements='str'),
            subscription_settings=dict(type='dict', options=dict(
                serve_json_at_base_subscription=dict(type='bool'),
                show_custom_remarks=dict(type='bool'), randomize_hosts=dict(type='bool'))),
            host_overrides=dict(type='dict', options=dict(
                server_description=dict(type='str'), vless_route_id=dict(type='raw'))),
            response_headers_add=dict(type='dict'),
            response_headers_remove=dict(type='list', elements='str'),
            hwid_settings=dict(type='raw'), custom_remarks=dict(type='raw'),
            subpage_config_uuid=dict(type='str'),
        )
    return options


def resolve_inbounds(module, client, items):
    uuids = []
    for item in items:
        if isinstance(item, str) and is_uuid(item):
            uuids.append(item)
            continue
        if isinstance(item, str):
            profile, tag = None, item
        elif isinstance(item, dict) and isinstance(item.get('tag'), str):
            profile, tag = item.get('profile'), item['tag']
        else:
            raise ValueError('Each inbound must be an inbound tag or UUID, or a dict '
                             'with a tag key and optionally a profile key, got: %r' % (item,))
        uuids.extend(resolve_for_check_mode(
            module, lambda: resolve_inbound_uuids(client, profile, [tag])[1],
            [tag if profile is None else '%s:%s' % (profile, tag)]))
    return sorted(set(uuids))


def external_params(module, client, params, current):
    resolved = dict(params)
    if params.get('templates') is not None:
        templates = []
        types = set()
        for name in params['templates']:
            template = resolve_for_check_mode(
                module, lambda: find_subscription_template(client, name, required=True),
                {'uuid': name, 'templateType': name})
            if template['templateType'] in types:
                raise ValueError('Only one subscription template per type may be assigned')
            types.add(template['templateType'])
            templates.append(dict(templateUuid=template['uuid'], templateType=template['templateType']))
        resolved['templates'] = sorted(templates, key=lambda t: t['templateType'])
    for option, api, mapping in [
        ('subscription_settings', 'subscriptionSettings', {
            'serve_json_at_base_subscription': 'serveJsonAtBaseSubscription',
            'show_custom_remarks': 'isShowCustomRemarks', 'randomize_hosts': 'randomizeHosts'}),
        ('host_overrides', 'hostOverrides', {
            'server_description': 'serverDescription', 'vless_route_id': 'vlessRouteId'}),
    ]:
        if params.get(option) is not None:
            value = dict((current or {}).get(api) or {})
            for key, field in mapping.items():
                if params[option].get(key) is not None:
                    v = params[option][key]
                    if key == 'server_description':
                        if len(v) > 30:
                            raise ValueError('server_description must be at most 30 characters')
                        v = v or None
                    if key == 'vless_route_id':
                        if v == '':
                            v = None
                        elif isinstance(v, bool) or not isinstance(v, int):
                            raise ValueError('vless_route_id must be an integer or an empty string to clear it')
                    value[field] = v
            resolved[option] = value
    for option in ('hwid_settings', 'custom_remarks'):
        if params.get(option) is not None:
            resolved[option] = parse_json_option(params[option], option, module)
            if resolved[option] is not None and not isinstance(resolved[option], dict):
                raise ValueError('%s must be a dict or the JSON string null' % option)
    return resolved


def plan_entity(module, client, kind, params):
    finder, max_length = RESOURCES[kind][4:]
    current = finder(client, params['name'])
    if kind == 'subscription_template' and current is not None and params['state'] != 'absent':
        current = client.get('/api/subscription-templates/%s' % current['uuid'], cached=True)
    plan = dict(name=params['name'], current=current, action='none', payload={},
                before={}, after={}, tags=None, kind=kind)
    if params['state'] == 'absent':
        if current is not None:
            plan.update(action='delete', before={'name': current['name']})
        return plan
    tags = validate_tags(params.get('tags'))
    resolved = dict(params)
    fields = []
    if kind == 'internal_squad':
        if params.get('inbounds') is not None:
            resolved['inbounds'] = resolve_inbounds(module, client, params['inbounds'])
        fields = [FieldSpec('inbounds', 'inbounds', kind='set',
                            from_api=lambda v: [i['uuid'] if isinstance(i, dict) else i for i in v or []])]
    elif kind == 'external_squad':
        resolved = external_params(module, client, params, current)
        fields = EXTERNAL_FIELDS
    else:
        if params.get('template_json') is not None and params.get('template_yaml') is not None:
            raise ValueError('template_json and template_yaml are mutually exclusive')
        if params.get('template_json') is not None:
            resolved['template_json'] = parse_json_option(params['template_json'], 'template_json', module)
            if not isinstance(resolved['template_json'], dict):
                raise ValueError('template_json must be a JSON object')
        fields = [FieldSpec('template_json', 'templateJson', kind='json'),
                  FieldSpec('template_yaml', 'encodedTemplateYaml',
                            to_api=lambda v: base64.b64encode(v.encode('utf-8')).decode('ascii'))]
        if current and params.get('template_type') not in (None, current['templateType']):
            raise ValueError('template_type cannot be changed on an existing template')
    patch, before, after = build_patch(resolved, current, fields)
    # JSON null is an explicit reset, unlike an omitted Ansible option.
    if kind == 'external_squad':
        for option, api in [('hwid_settings', 'hwidSettings'), ('custom_remarks', 'customRemarks')]:
            if params.get(option) is not None and resolved[option] is None and (current or {}).get(api) is not None:
                patch[api], before[api], after[api] = None, current[api], None
    if tags_differ(tags, (current or {}).get('tags')):
        plan['tags'] = tags
        before['tags'], after['tags'] = (current or {}).get('tags') or [], tags
    if current is None:
        name = params['name']
        if is_uuid(name):
            raise ValueError('%s %r not found; entities are created by name, not by UUID' % (kind, name))
        if not 2 <= len(name) <= max_length:
            raise ValueError('%s name must be 2 to %d characters long' % (kind, max_length))
        if kind == 'internal_squad' and params.get('inbounds') is None:
            raise ValueError('inbounds is required when creating internal squad %r' % name)
        if kind == 'subscription_template' and params.get('template_type') is None:
            raise ValueError('template_type is required when creating subscription template %r' % name)
        plan['action'] = 'create'
        after['name'] = name
        if kind == 'subscription_template':
            after['templateType'] = params['template_type']
    elif patch or plan['tags'] is not None:
        plan['action'] = 'update'
    plan.update(payload=patch, before=before if current else {}, after=after)
    return plan


def entity_result(module, plan, entity):
    result = dict(changed=plan['action'] != 'none')
    if entity is not None:
        result[RESOURCES[plan['kind']][2]] = entity
    if result['changed'] and module._diff:
        result['diff'] = dict(before=plan['before'], after=plan['after'])
    return result


def apply_entity(module, client, plan, on_write=None):
    collection = RESOURCES[plan['kind']][0]
    path = '/api/%s' % collection
    action, entity = plan['action'], plan['current']
    if action == 'none':
        return entity_result(module, plan, entity)
    if module.check_mode:
        entity = None if action == 'delete' else dict(entity or {}, **plan['after'])
        return entity_result(module, plan, entity)
    if action == 'delete':
        client.delete('%s/%s' % (path, entity['uuid']))
        if on_write:
            on_write()
        return entity_result(module, plan, None)
    payload = dict(plan['payload'])
    if action == 'create':
        create = {'name': plan['name']}
        if plan['kind'] == 'internal_squad':
            create['inbounds'] = payload.pop('inbounds')
        elif plan['kind'] == 'subscription_template':
            create['templateType'] = plan['after']['templateType']
        entity = client.post(path, create)
        if on_write:
            on_write()
    if payload:
        entity = client.patch(path, dict(payload, uuid=entity['uuid']))
        if on_write:
            on_write()
    if plan['tags'] is not None:
        entity = set_tags(client, collection, entity, plan['tags'])
        if on_write:
            on_write()
    return entity_result(module, plan, entity)


def run_single(module, client, kind):
    touched = []
    try:
        result = apply_entity(module, client, plan_entity(module, client, kind, module.params),
                              on_write=lambda: touched.append(True))
    except RemnawaveApiError as exc:
        module.fail_json(msg=str(exc), status=exc.status, error_code=exc.error_code,
                         changed=bool(touched))
    module.exit_json(**result)


def run_batch(module, client, kind):
    collection, key, item, listing, finder, dummy = RESOURCES[kind]
    entries = module.params[key]
    paths = ['/api/%s' % collection]
    if kind == 'internal_squad' and any(e.get('inbounds') is not None and e['state'] != 'absent' for e in entries):
        paths.append('/api/config-profiles')
    if kind == 'external_squad' and any(e.get('templates') is not None and e['state'] != 'absent' for e in entries):
        paths.append('/api/subscription-templates')
    client.prefetch(paths)
    original = listing(client)
    if kind == 'subscription_template':
        wanted = set(e['name'] for e in entries if e['state'] != 'absent')
        client.prefetch(['/api/subscription-templates/%s' % t['uuid'] for t in original
                         if t['name'] in wanted or t['uuid'] in wanted])
    plans, claimed = [], {}
    for index, entry in enumerate(entries):
        label = '%s[%d] (%r)' % (key, index, entry['name'])
        try:
            plan = plan_entity(module, client, kind, entry)
            identity = (plan['current'] or {}).get('uuid') or plan['name']
            if identity in claimed:
                raise ValueError('%s and %s address the same entity; declare each once' % (claimed[identity], label))
            claimed[identity] = label
            plan['label'] = label
            plans.append(plan)
        except (ValueError, RemnawaveApiError) as exc:
            module.fail_json(msg='%s: %s. Nothing was changed.' % (label, exc))
    results = [None] * len(plans)
    failure = None
    touched = []
    if module.check_mode:
        results = [apply_entity(module, client, p) for p in plans]
    else:
        def record(index, result):
            results[index] = result

        def carry_out(plan):
            # A plan can take several writes. Even when a later one fails,
            # the earlier writes cannot be rolled back.
            return [apply_entity(module, client, plan,
                                 on_write=lambda: touched.append(plan))]

        for actions in [('delete',), ('none', 'update'), ('create',)]:
            indices = [i for i, p in enumerate(plans) if p['action'] in actions]
            workers = module.params['parallelism']
            if actions == ('create',) and not module.params['order']:
                workers = 1
            outcomes = client.run_parallel(
                [lambda p=plans[i]: carry_out(p) for i in indices], workers)
            failure = collect_outcomes(plans, [[i] for i in indices], outcomes, record)
            if failure:
                break
    if not failure and module.params['order']:
        exc = arrange(module, client, collection, item, plans, results, original, request_key='items')
        if exc:
            failure = (plans, exc)
    # Read back after writes, also after a partly applied failure.
    if not module.check_mode and (failure or any(r and r['changed'] for r in results)):
        fresh = dict((e['uuid'], e) for e in listing(client))
        for result in results:
            entity = (result or {}).get(item)
            if entity and entity.get('uuid') in fresh:
                if kind == 'subscription_template':
                    result[item] = client.get('/api/subscription-templates/%s' % entity['uuid'], cached=True)
                else:
                    result[item] = fresh[entity['uuid']]
    output, diffs = [], []
    for plan, result in zip(plans, results):
        if result is None:
            continue
        diff = result.pop('diff', None)
        if diff:
            diffs.append(dict(diff, before_header=plan['label'], after_header=plan['label']))
        result.update(name=plan['name'], action=result.get('action', plan['action']))
        output.append(result)
    kwargs = dict(changed=bool(touched) or any(r['changed'] for r in output), results=output)
    if diffs:
        kwargs['diff'] = diffs
    if failure:
        failed, exc = failure
        module.fail_json(msg='%s: %s' % (', '.join(p['label'] for p in failed), exc),
                         status=exc.status, error_code=exc.error_code, **kwargs)
    module.exit_json(**kwargs)
