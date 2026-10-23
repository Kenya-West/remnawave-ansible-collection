# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Planning and applying the desired state of nodes.

Shared by the node module, which manages one node per task, and the nodes
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
    parse_traffic_limit, resolve_for_check_mode, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    bulk_host_action, find_infra_provider, find_node, hosts_linked_to_node,
    list_nodes, resolve_inbound_uuids,
)


# The fields the panel sets on many nodes at once: these through its bulk
# update, the config profile through its bulk profile modification.
BULK_UPDATE_FIELDS = frozenset(
    ['countryCode', 'consumptionMultiplier', 'tags', 'note', 'providerUuid'])


def node_options():
    """The options describing one node, without the connection options."""
    return dict(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=STATE_CHOICES, default='present'),
        linked_hosts=dict(type='str', default='ignore',
                          choices=['ignore', 'enable', 'disable', 'delete']),
        address=dict(type='str'),
        port=dict(type='int'),
        config_profile=dict(type='str'),
        inbounds=dict(type='list', elements='str'),
        traffic_tracking=dict(type='bool'),
        traffic_limit=dict(type='raw'),
        notify_percent=dict(type='int'),
        traffic_reset_day=dict(type='int'),
        country_code=dict(type='str'),
        consumption_multiplier=dict(type='float'),
        tags=dict(type='list', elements='str'),
        note=dict(type='str'),
        provider=dict(type='str'),
    )


def node_listings(entries):
    """The panel listings that planning these node entries reads.

    Fetched together up front (RemnawaveClient.prefetch), they cost one
    round trip to the panel rather than one each.
    """
    paths = ['/api/nodes']
    if any(e['state'] != 'absent' and (e['inbounds'] is not None
                                       or e['config_profile'] is not None)
           for e in entries):
        paths.append('/api/config-profiles')
    if any(e['linked_hosts'] != 'ignore' for e in entries):
        paths.append('/api/hosts')
    if any(e['state'] != 'absent' and e['provider'] for e in entries):
        paths.append('/api/infra-billing/providers')
    return paths


def current_config_profile(value):
    value = value or {}
    return {
        'activeConfigProfileUuid': value.get('activeConfigProfileUuid'),
        'activeInbounds': sorted(
            i.get('uuid') for i in (value.get('activeInbounds') or [])),
    }


def build_fields(module, client, params):
    fields = [
        FieldSpec('address', 'address'),
        FieldSpec('port', 'port'),
        FieldSpec('traffic_tracking', 'isTrafficTrackingActive'),
        FieldSpec('traffic_limit', 'trafficLimitBytes',
                  to_api=parse_traffic_limit),
        FieldSpec('notify_percent', 'notifyPercent'),
        FieldSpec('traffic_reset_day', 'trafficResetDay'),
        FieldSpec('country_code', 'countryCode', to_api=lambda v: v.upper()),
        FieldSpec('consumption_multiplier', 'consumptionMultiplier'),
        FieldSpec('tags', 'tags', kind='set', to_api=validate_tags),
        FieldSpec('note', 'note', to_api=lambda v: v or None),
        # Resolved below; an empty string unlinks the provider.
        FieldSpec('provider', 'providerUuid', to_api=lambda v: v or None),
    ]
    resolved = dict(params)
    if params['provider']:
        resolved['provider'] = resolve_for_check_mode(
            module,
            lambda: find_infra_provider(client, params['provider'],
                                        required=True)['uuid'],
            params['provider'])
    if params['config_profile'] is not None or params['inbounds'] is not None:
        # The inbounds alone suffice: their tags are unique across profiles,
        # so they name their profile too.
        if params['inbounds'] is None:
            raise ValueError('config_profile requires inbounds')
        profile_uuid, inbound_uuids = resolve_for_check_mode(
            module,
            lambda: resolve_inbound_uuids(
                client, params['config_profile'], params['inbounds']),
            (params['config_profile'], list(params['inbounds'])))
        resolved['config_profile'] = {
            'activeConfigProfileUuid': profile_uuid,
            'activeInbounds': sorted(inbound_uuids),
        }
        fields.append(FieldSpec(
            'config_profile', 'configProfile', kind='json',
            from_api=current_config_profile))
    return fields, resolved


def plan_cascade(client, action, node, before, after):
    """The linked_hosts change of one node, or None when there is none.

    Returns ``{'action': ..., 'hosts': [...]}`` with the hosts it changes,
    and adds them to the ``before``/``after`` diff.
    """
    if action == 'ignore' or node is None:
        return None
    linked = hosts_linked_to_node(client, node['uuid'])
    if action == 'delete':
        targets = linked
    else:
        wanted_disabled = (action == 'disable')
        targets = [h for h in linked
                   if bool(h.get('isDisabled', False)) != wanted_disabled]
    if not targets:
        return None
    before['linkedHosts'] = dict(
        (h.get('remark'), 'disabled' if h.get('isDisabled') else 'enabled')
        for h in targets)
    after['linkedHosts'] = dict(
        (h.get('remark'), 'absent' if action == 'delete' else '%sd' % action)
        for h in targets)
    return dict(action=action, hosts=targets)


def plan_node(module, client, params):
    """Work out what one node needs, without changing anything.

    ``params`` holds the options of one node. Returns a dict with the
    ``action`` to take (``create``, ``update``, ``delete`` or ``none``),
    the node as found on the panel (``current``), the request ``payload``,
    the enabled-ness to switch to (``enable``, None to leave it), the
    linked hosts to change (``cascade``) and the ``before``/``after`` diff.
    """
    name = params['name']
    current = find_node(client, name)
    plan = dict(name=name, current=current, action='none', payload=None,
                enable=None, cascade=None, before={}, after={})

    if params['state'] == 'absent':
        if current is None:
            # Without the node there is no binding left to resolve, so any
            # cascade would have to guess which hosts were linked.
            return plan
        plan.update(action='delete', cascade=plan_cascade(
            client, params['linked_hosts'], current,
            plan['before'], plan['after']))
        plan['before']['name'] = name
        return plan

    wanted_enabled = desired_enabled(params['state'])
    fields, resolved = build_fields(module, client, params)
    patch, before, after = build_patch(resolved, current, fields)
    plan.update(before=before, after=after)

    if current is None:
        missing = [opt for opt in ('address', 'inbounds')
                   if params[opt] is None]
        if missing:
            raise ValueError('Creating node %r requires: %s'
                             % (name, ', '.join(missing)))
        payload = dict(patch)
        payload['name'] = name
        after['name'] = name
        if wanted_enabled is False:
            # Nodes are created enabled; disabled right after.
            after['isDisabled'] = True
            plan['enable'] = False
        plan.update(action='create', payload=payload)
        return plan

    if (wanted_enabled is not None
            and (not current.get('isDisabled', False)) != wanted_enabled):
        plan['enable'] = wanted_enabled
        before['isDisabled'] = current.get('isDisabled')
        after['isDisabled'] = not wanted_enabled
    if patch:
        payload = dict(patch)
        payload['uuid'] = current['uuid']
        plan['payload'] = payload
    if patch or plan['enable'] is not None:
        plan['action'] = 'update'
    plan['cascade'] = plan_cascade(client, params['linked_hosts'], current,
                                   before, after)
    return plan


def node_changed(plan):
    return plan['action'] != 'none' or plan['cascade'] is not None


def node_result(module, plan, node):
    """The module result for one carried-out plan.

    ``changed``, the remarks of the ``linked_hosts`` changed, the ``node``
    as it is now (or would be) unless it is gone, and a ``diff`` in diff
    mode.
    """
    changed = node_changed(plan)
    cascade = plan['cascade']
    result = dict(changed=changed, linked_hosts=sorted(
        h.get('remark') for h in (cascade or {}).get('hosts', [])))
    if node is not None:
        result['node'] = node
    if changed and module._diff:
        result['diff'] = dict(before=plan['before'], after=plan['after'])
    return result


def apply_node_plan(module, client, plan):
    """Carry out a plan (only pretending in check mode)."""
    action = plan['action']
    current = plan['current']
    cascade = plan['cascade']
    if action == 'delete':
        if not module.check_mode:
            # Hosts first: after the node is gone the binding cannot be
            # resolved.
            if cascade:
                bulk_host_action(client, cascade['action'],
                                 [h['uuid'] for h in cascade['hosts']])
            client.delete('/api/nodes/%s' % current['uuid'])
        return node_result(module, plan, None)

    if action == 'create':
        if module.check_mode:
            return node_result(module, plan, plan['payload'])
        created = client.post('/api/nodes', plan['payload'])
        if plan['enable'] is False:
            client.post('/api/nodes/%s/actions/disable' % created['uuid'])
            created = find_node(client, plan['name'], required=True)
        return node_result(module, plan, created)

    if not module.check_mode:
        if plan['enable'] is not None:
            client.post('/api/nodes/%s/actions/%s' % (
                current['uuid'], 'enable' if plan['enable'] else 'disable'))
        if plan['payload']:
            client.patch('/api/nodes', plan['payload'])
        if cascade:
            bulk_host_action(client, cascade['action'],
                             [h['uuid'] for h in cascade['hosts']])
    if module.check_mode or not node_changed(plan):
        return node_result(module, plan, current)
    return node_result(module, plan,
                       find_node(client, plan['name'], required=True))


def set_nodes_enabled(client, uuids, enabled):
    """Enable or disable many nodes in one request.

    A panel without the bulk endpoint gets one request per node instead,
    which answers with each node.
    """
    try:
        client.post('/api/nodes/bulk-actions', {
            'uuids': list(uuids), 'action': 'ENABLE' if enabled else 'DISABLE'})
        return None
    except RemnawaveApiError as exc:
        if exc.status != 404:
            raise
    return [client.post('/api/nodes/%s/actions/%s'
                        % (uuid, 'enable' if enabled else 'disable'))
            for uuid in uuids]


def update_fields(plan):
    """An update's payload without the uuid: what it changes."""
    return dict((k, v) for k, v in plan['payload'].items() if k != 'uuid')


def bulk_updatable(fields):
    """Whether the panel can give many nodes these fields in one request."""
    return set(fields) <= BULK_UPDATE_FIELDS or set(fields) == set(['configProfile'])


def update_nodes(client, plans):
    """Send one update shared by every plan of ``plans``.

    Several nodes take one bulk request when the panel has one for the
    fields changed; it answers with no content. Otherwise, or on a panel
    without it, each node gets a request of its own, answered with it.
    """
    fields = update_fields(plans[0])
    uuids = [p['current']['uuid'] for p in plans]
    if len(plans) > 1 and bulk_updatable(fields):
        try:
            if 'configProfile' in fields:
                client.post('/api/nodes/bulk-actions/profile-modification', {
                    'uuids': uuids, 'configProfile': fields['configProfile']})
            else:
                client.post('/api/nodes/bulk-actions/update',
                            {'uuids': uuids, 'fields': fields})
            return None
        except RemnawaveApiError as exc:
            if exc.status != 404:
                raise
    return [client.patch('/api/nodes', p['payload']) for p in plans]


def delete_node(client, uuid):
    client.delete('/api/nodes/%s' % uuid)


def change_linked_hosts(client, action, plans):
    """Apply one linked_hosts action for several nodes in one request."""
    uuids = []
    for plan in plans:
        for host in plan['cascade']['hosts']:
            if host['uuid'] not in uuids:
                uuids.append(host['uuid'])
    bulk_host_action(client, action, uuids)


def writes_of(plan):
    """How many writes carrying out a plan takes in a batch."""
    count = 1 if plan['cascade'] else 0
    if plan['action'] in ('create', 'delete'):
        count += 1
    if plan['action'] == 'create' and plan['enable'] is False:
        count += 1
    if plan['action'] == 'update':
        count += (plan['enable'] is not None) + bool(plan['payload'])
    return count


def apply_node_plans(module, client, plans, parallelism=DEFAULT_PARALLELISM,
                     ordered=False):
    """Carry out the plans of a batch with as few requests as it takes.

    In turn: the linked hosts, in one bulk request per action, before any
    node is deleted; deletions; enabling and disabling, in one bulk request
    each; updates, where nodes given the very same change share one bulk
    request if the panel has one for those fields; creations; and then the
    nodes created disabled are disabled, in one bulk request. Each step
    runs up to ``parallelism`` requests at a time, except creations, which
    go one by one in list order unless the batch is ``ordered`` - put in
    order afterwards by arrange_nodes.

    Returns ``(results, failure)``. ``results`` follows ``plans`` and holds
    None for every plan not carried out in full; ``failure`` is None, or
    the ``(plans, error)`` of the first write the panel rejected, after
    which nothing more is written. A node is reported as its last write
    answered, or as found when no write answered with it.
    """
    if module.check_mode:
        return [apply_node_plan(module, client, p) for p in plans], None

    remaining = [writes_of(p) for p in plans]
    answered = {}

    def record(index, node):
        remaining[index] -= 1
        if node is not None:
            answered[index] = node

    def step(groups, workers=parallelism):
        """Run ``(indices, call)`` groups; workers=None: one by one, up to
        the first rejected."""
        if workers is None:
            for group in groups:
                failure = step([group])
                if failure:
                    return failure
            return None
        outcomes = client.run_parallel([call for dummy, call in groups],
                                       workers)
        return collect_outcomes(plans, [indices for indices, dummy in groups],
                                outcomes, record)

    def where(test):
        return [i for i, p in enumerate(plans) if test(p)]

    def cascades():
        by_action = {}
        for index in where(lambda p: p['cascade']):
            by_action.setdefault(plans[index]['cascade']['action'], []).append(index)
        return [(indices, lambda a=action, ix=indices: change_linked_hosts(
            client, a, [plans[i] for i in ix]))
            for action, indices in sorted(by_action.items())]

    def deletions():
        return [([i], lambda i=i: delete_node(client, plans[i]['current']['uuid']))
                for i in where(lambda p: p['action'] == 'delete')]

    def switches(test=lambda p: p['action'] == 'update', uuid=None):
        uuid = uuid or (lambda i: plans[i]['current']['uuid'])
        groups = []
        for enabled in (True, False):
            indices = where(lambda p: test(p) and p['enable'] is enabled)
            if indices:
                groups.append((indices, lambda e=enabled, ix=indices:
                               set_nodes_enabled(client, [uuid(i) for i in ix], e)))
        return groups

    def updates():
        groups = {}
        order = []
        for index in where(lambda p: p['action'] == 'update' and p['payload']):
            fields = update_fields(plans[index])
            key = (json.dumps(fields, sort_keys=True) if bulk_updatable(fields)
                   else index)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(index)
        return [(groups[key], lambda ix=groups[key]: update_nodes(
            client, [plans[i] for i in ix])) for key in order]

    def creations():
        return [([i], lambda i=i: [client.post('/api/nodes', plans[i]['payload'])])
                for i in where(lambda p: p['action'] == 'create')]

    def created(plan):
        return plan['action'] == 'create'

    failure = (step(cascades()) or step(deletions()) or step(switches())
               or step(updates())
               or step(creations(), parallelism if ordered else None)
               or step(switches(created, lambda i: answered[i]['uuid'])))

    results = [None] * len(plans)
    for index, plan in enumerate(plans):
        if remaining[index]:
            continue
        node = None
        if plan['action'] != 'delete':
            node = answered.get(index, plan['current'])
        results[index] = node_result(module, plan, node)
    return results, failure


def arrange_nodes(module, client, plans, results, listing):
    """Put the nodes of a carried-out batch in list order; see arrange.

    ``listing`` is the panel's nodes as planning found them. Returns the
    RemnawaveApiError of a rejected reorder, or None.
    """
    return arrange(module, client, 'nodes', 'node', plans, results, listing)


def refresh_nodes(client, results):
    """Report the nodes of ``results`` as the panel now holds them.

    Bulk requests answer without the nodes, and a reorder moves them, so
    after a batch has written anything the nodes are read again, in one
    request, rather than pieced together from the answers.
    """
    fresh = dict((n['uuid'], n) for n in list_nodes(client))
    for result in results:
        node = (result or {}).get('node')
        if node and node.get('uuid') in fresh:
            result['node'] = fresh[node['uuid']]


def entry_label(index, entry):
    return 'nodes[%d] (%r)' % (index, entry.get('name'))


def plan_nodes(module, client, entries):
    """Plan every entry of a batch; raises over the first bad one.

    Entries are planned against the panel as it is before the batch, so
    one entry cannot build on another's change, and each node may be
    declared only once. Nor may two entries give one linked host different
    linked_hosts actions. Raised errors name the offending entry.
    """
    client.prefetch(node_listings(entries))
    plans = []
    claimed = {}
    cascaded = {}
    for index, entry in enumerate(entries):
        label = entry_label(index, entry)
        try:
            plan = plan_node(module, client, entry)
        except RemnawaveApiError as exc:
            raise RemnawaveApiError('%s: %s' % (label, exc), status=exc.status,
                                    error_code=exc.error_code, body=exc.body)
        except ValueError as exc:
            raise ValueError('%s: %s' % (label, exc))

        if plan['name'] in claimed:
            raise ValueError('%s and %s address the same node; declare each '
                             'node once' % (claimed[plan['name']], label))
        claimed[plan['name']] = label

        cascade = plan['cascade']
        for host in (cascade or {}).get('hosts', []):
            other = cascaded.get(host['uuid'])
            if other and other[1] != cascade['action']:
                raise ValueError(
                    '%s would %s host %r, and %s would %s it; a host bound to '
                    'several nodes can take only one linked_hosts action'
                    % (other[0], other[1], host.get('remark'), label,
                       cascade['action']))
            cascaded[host['uuid']] = (label, cascade['action'])
        plan['label'] = label
        plans.append(plan)
    return plans
