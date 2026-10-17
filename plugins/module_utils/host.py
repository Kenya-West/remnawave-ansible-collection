# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Planning and applying the desired state of hosts.

Shared by the host module, which manages one host per task, and the hosts
module, which manages many in a single task. Planning only reads the panel
and applying only writes to it, so a batch can plan every entry - and
refuse the whole batch over a bad one - before it changes anything.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json

from ansible_collections.kenyawest.remnawave.plugins.module_utils.batch import (
    DEFAULT_PARALLELISM, arrange, collect_outcomes,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    STATE_CHOICES, FieldSpec, build_patch, desired_enabled,
    resolve_for_check_mode, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    bulk_host_action, bulk_update_hosts, find_host, resolve_inbound_uuids,
    resolve_internal_squad_uuids, resolve_node_uuids,
)


# Only one of them must be set, depending on which identifies the host.
HOST_REQUIRED_IF = [('identify_by', 'remark', ['remark']),
                    ('identify_by', 'address', ['address'])]

def host_listings(entries):
    """The panel listings that planning these host entries reads.

    Fetched together up front (RemnawaveClient.prefetch), they cost one
    round trip to the panel rather than one each, as planning would read
    them one after another.
    """
    paths = ['/api/hosts']
    if any(e['state'] != 'absent' and e['nodes'] is not None for e in entries):
        paths.append('/api/nodes')
    if any(e['state'] != 'absent' and e['internal_squads'] is not None
           for e in entries):
        paths.append('/api/internal-squads')
    if any(e['state'] != 'absent' and e['inbound'] is not None for e in entries):
        paths.append('/api/config-profiles')
    return paths


def host_options():
    """The options describing one host, without the connection options."""
    return dict(
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
        vless_route_id=dict(type='raw'),
        override_sni_from_address=dict(type='bool'),
        keep_sni_blank=dict(type='bool'),
        exclude_from_subscription_types=dict(
            type='list', elements='str',
            choices=['XRAY_JSON', 'XRAY_BASE64', 'MIHOMO', 'STASH', 'CLASH',
                     'SINGBOX']),
        internal_squads=dict(type='dict', options=dict(
            mode=dict(type='str', choices=['exclude', 'allow_only'],
                      required=True),
            squads=dict(type='list', elements='str', required=True),
        )),
    )


def to_route_id(value):
    """Normalize the vless_route_id option into an int or None.

    Empty string clears the field, matching how the other nullable host
    options are cleared.
    """
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('vless_route_id must be an integer between 0 and '
                         '65535, or an empty string to clear it')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError('vless_route_id must be an integer between 0 and '
                         '65535, or an empty string to clear it, got %r'
                         % (value,))
    if not 0 <= number <= 65535:
        raise ValueError('vless_route_id must be between 0 and 65535, got %d'
                         % number)
    return number


def build_fields(module, client, params):
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
        FieldSpec('tags', 'tags', kind='set', to_api=validate_tags),
        FieldSpec('server_description', 'serverDescription',
                  to_api=lambda v: v or None),
        FieldSpec('vless_route_id', 'vlessRouteId', to_api=to_route_id),
        FieldSpec('override_sni_from_address', 'overrideSniFromAddress'),
        FieldSpec('keep_sni_blank', 'keepSniBlank'),
        FieldSpec('exclude_from_subscription_types',
                  'excludeFromSubscriptionTypes', kind='set'),
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

    if params['internal_squads'] is not None:
        squads = params['internal_squads']
        resolved['internal_squads'] = {
            'mode': squads['mode'].upper(),
            'squads': sorted(resolve_for_check_mode(
                module,
                lambda: resolve_internal_squad_uuids(client, squads['squads']),
                list(squads['squads']))),
        }
        fields.append(FieldSpec(
            'internal_squads', 'internalSquads', kind='json',
            from_api=lambda v: {
                'mode': (v or {}).get('mode'),
                'squads': sorted((v or {}).get('squads') or []),
            }))

    if params['config_profile'] is not None or params['inbound'] is not None:
        # The inbound alone suffices: its tag is unique across profiles, so
        # it names its profile too.
        if params['inbound'] is None:
            raise ValueError('config_profile requires inbound')
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


def plan_host(module, client, params):
    """Work out what one host needs, without changing anything.

    ``params`` holds the options of one host. Returns a dict with the
    ``action`` to take (``create``, ``update``, ``delete`` or ``none``),
    the host as found on the panel (``current``), the request ``payload``
    and the ``before``/``after`` diff.
    """
    identify_by = params['identify_by']
    identifier = params[identify_by]
    if identifier is None:
        raise ValueError(
            'Option %s is required, because identify_by=%s makes it the '
            'identifier of the host' % (identify_by, identify_by))
    current = find_host(client, identifier, key=identify_by)
    plan = dict(identify_by=identify_by, identifier=identifier,
                current=current, action='none', payload=None,
                before={}, after={})

    if params['state'] == 'absent':
        if current is not None:
            plan.update(action='delete', before={identify_by: identifier})
        return plan

    fields, resolved = build_fields(module, client, params)
    patch, before, after = build_patch(resolved, current, fields)

    if current is None:
        missing = [opt for opt in ('inbound', 'address', 'port')
                   if params[opt] is None]
        if missing:
            raise ValueError('Creating host %r requires: %s'
                             % (identifier, ', '.join(missing)))
        payload = dict(patch)
        # The API always wants a remark; when hosts are addressed by domain
        # and no remark is given, the domain is the obvious display name.
        payload['remark'] = params['remark'] or params['address']
        plan.update(action='create', payload=payload,
                    after=dict(after, remark=payload['remark']))
        return plan

    if patch:
        payload = dict(patch)
        payload['uuid'] = current['uuid']
        plan.update(action='update', payload=payload,
                    before=before, after=after)
    return plan


def host_result(module, plan, host):
    """The module result for one carried-out plan.

    ``changed``, the ``host`` as it is now (or would be) unless it is gone,
    and a ``diff`` in diff mode.
    """
    result = dict(changed=plan['action'] != 'none')
    if host is not None:
        result['host'] = host
    if plan['action'] != 'none' and module._diff:
        result['diff'] = dict(before=plan['before'], after=plan['after'])
    return result


def apply_host_plan(module, client, plan):
    """Carry out a plan (only pretending in check mode)."""
    action = plan['action']
    current = plan['current']
    if action == 'none':
        return host_result(module, plan, current)
    if action == 'delete':
        if not module.check_mode:
            client.delete('/api/hosts/%s' % current['uuid'])
        return host_result(module, plan, None)
    if action == 'create':
        return host_result(module, plan, (
            plan['payload'] if module.check_mode
            else client.post('/api/hosts', plan['payload'])))
    return host_result(module, plan, (
        current if module.check_mode
        else client.patch('/api/hosts', plan['payload'])))


def update_fields(plan):
    """An update's payload without the uuid: what it changes."""
    return dict((k, v) for k, v in plan['payload'].items() if k != 'uuid')


def apply_update_group(client, plans):
    """Send one update shared by every plan of ``plans``.

    Returns each host as it is afterwards. Several hosts take one bulk
    request, which answers with no content, so they are reported as found
    with the change applied. A panel without the bulk endpoint gets one
    request per host instead.
    """
    if len(plans) > 1:
        fields = update_fields(plans[0])
        try:
            bulk_update_hosts(client, [p['current']['uuid'] for p in plans],
                              fields)
            return [dict(p['current'], **fields) for p in plans]
        except RemnawaveApiError as exc:
            if exc.status != 404:
                raise
    return [client.patch('/api/hosts', p['payload']) for p in plans]


def apply_host_plans(module, client, plans, parallelism=DEFAULT_PARALLELISM,
                     ordered=False):
    """Carry out the plans of a batch with as few requests as it takes.

    Deletions go first, in one bulk request, so the remarks and addresses
    they free are free for what follows. Then updates: hosts given the very
    same change share one bulk request, and these requests run up to
    ``parallelism`` at a time. Creations come last. The panel places each
    new host after the existing ones, so they go one by one in list order,
    unless the batch is ``ordered`` - put in order afterwards by
    arrange_hosts - in which case they run up to ``parallelism`` at a time
    too.

    Returns ``(results, failure)``. ``results`` follows ``plans`` and holds
    None for every plan not carried out; ``failure`` is None, or the
    ``(plans, error)`` of the first write the panel rejected, after which
    nothing more is written.
    """
    if module.check_mode:
        return [apply_host_plan(module, client, p) for p in plans], None

    results = [None] * len(plans)
    for index, plan in enumerate(plans):
        if plan['action'] == 'none':
            results[index] = host_result(module, plan, plan['current'])

    deletes = [i for i, p in enumerate(plans) if p['action'] == 'delete']
    if deletes:
        try:
            bulk_host_action(client, 'delete',
                             [plans[i]['current']['uuid'] for i in deletes])
        except RemnawaveApiError as exc:
            return results, ([plans[i] for i in deletes], exc)
        for i in deletes:
            results[i] = host_result(module, plans[i], None)

    groups = {}
    order = []
    for index, plan in enumerate(plans):
        if plan['action'] == 'update':
            key = json.dumps(update_fields(plan), sort_keys=True)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(index)
    outcomes = client.run_parallel(
        [lambda indices=groups[key]: apply_update_group(
            client, [plans[i] for i in indices]) for key in order],
        parallelism)
    failure = collect_host_outcomes(module, plans, results,
                                    [groups[key] for key in order], outcomes)
    if failure:
        return results, failure

    creates = [i for i, p in enumerate(plans) if p['action'] == 'create']
    if ordered:
        outcomes = client.run_parallel(
            [lambda plan=plans[i]: [client.post('/api/hosts', plan['payload'])]
             for i in creates],
            parallelism)
        return results, collect_host_outcomes(module, plans, results,
                                              [[i] for i in creates], outcomes)
    for index in creates:
        try:
            host = client.post('/api/hosts', plans[index]['payload'])
        except RemnawaveApiError as exc:
            return results, ([plans[index]], exc)
        results[index] = host_result(module, plans[index], host)
    return results, None


def collect_host_outcomes(module, plans, results, groups, outcomes):
    """Record the hosts concurrent writes left; see collect_outcomes."""
    def record(index, host):
        results[index] = host_result(module, plans[index], host)
    return collect_outcomes(plans, groups, outcomes, record)


def arrange_hosts(module, client, plans, results, listing):
    """Put the hosts of a carried-out batch in list order; see arrange.

    ``listing`` is the panel's hosts as planning found them. Returns the
    RemnawaveApiError of a rejected reorder, or None.
    """
    return arrange(module, client, 'hosts', 'host', plans, results, listing)


def entry_label(index, entry):
    identify_by = entry['identify_by']
    return 'hosts[%d] (%s %r)' % (index, identify_by, entry.get(identify_by))


def plan_hosts(module, client, entries):
    """Plan every entry of a batch; raises over the first bad one.

    Entries are planned against the panel as it is before the batch, so
    one entry cannot build on another's change, and each host may be
    declared only once. Raised errors name the offending entry.
    """
    client.prefetch(host_listings(entries))
    plans = []
    claimed = {}
    for index, entry in enumerate(entries):
        label = entry_label(index, entry)
        try:
            plan = plan_host(module, client, entry)
        except RemnawaveApiError as exc:
            raise RemnawaveApiError('%s: %s' % (label, exc), status=exc.status,
                                    error_code=exc.error_code, body=exc.body)
        except ValueError as exc:
            raise ValueError('%s: %s' % (label, exc))

        current = plan['current']
        if current is not None:
            key = ('uuid', current['uuid'])
        else:
            key = (plan['identify_by'], plan['identifier'])
        if key in claimed:
            raise ValueError('%s and %s address the same host; declare each '
                             'host once' % (claimed[key], label))
        claimed[key] = label
        plan['label'] = label
        plans.append(plan)
    return plans
