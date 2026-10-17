# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""What the batch modules (hosts, nodes) share in carrying out their plans.

A plan is a dict describing one entry's change: at least its ``action``
(``create``, ``update``, ``delete`` or ``none``) and the entity as found
(``current``). The helpers here run the writes of many plans concurrently
and put the entities of a batch in list order.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)


# How many writes a batch has in flight at once, unless told otherwise.
DEFAULT_PARALLELISM = 4


def collect_outcomes(plans, groups, outcomes, record):
    """Take in what concurrent writes did, each for a group of plans.

    An outcome is the list of entities its group's write left, one per plan
    (None where the write answered without it), or the error it raised.
    ``record(index, entity)`` is called for every plan of a group written.
    Returns the ``(plans, error)`` of the first group the panel rejected, or
    None; errors other than the panel's are raised.
    """
    failure = None
    for indices, outcome in zip(groups, outcomes):
        if isinstance(outcome, RemnawaveApiError):
            failure = failure or ([plans[i] for i in indices], outcome)
        elif isinstance(outcome, Exception):
            raise outcome
        else:
            for i, entity in zip(indices, outcome or [None] * len(indices)):
                record(i, entity)
    return failure


def arrange(module, client, collection, item, plans, results, listing):
    """Put the entities of a carried-out batch in list order, in one request.

    ``collection`` names the panel's collection (``hosts``, ``nodes``), and
    ``item`` the key of the entity in a result (``host``, ``node``).
    ``listing`` is the panel's entities as planning found them.

    The entities the batch keeps take the places in the panel's order that
    they hold between them, in the order of ``plans``; every other entity
    keeps its place, so what the batch does not declare is never moved
    relative to anything. Places are ``viewPosition``s, which a reorder
    request sets to exactly the values given - so they are shuffled among
    the batch's entities, unless two of these share a position, which
    leaves their order to chance; then every entity is renumbered from 1,
    in the order wanted.

    An entity that only moves is reported as an update. Returns the
    RemnawaveApiError of a rejected reorder, or None.
    """
    gone = set(p['current']['uuid'] for p in plans if p['action'] == 'delete')
    found = sorted(enumerate(e for e in listing if e['uuid'] not in gone),
                   key=lambda pair: (pair[1].get('viewPosition') or 0, pair[0]))
    layout = [(e['uuid'], e.get('viewPosition') or 0) for dummy, e in found]
    last = max([position for dummy, position in layout] or [0])

    keys = []
    for index, plan in enumerate(plans):
        if plan['action'] == 'create':
            entity = results[index].get(item) or {}
            position = None if module.check_mode else entity.get('viewPosition')
            if position is None:
                # Not created yet (check mode), or the panel did not say
                # where: new entities go after the existing ones.
                last += 1
                position = last
            key = ('new', index) if module.check_mode else entity['uuid']
            layout.append((key, position))
        elif plan['current'] is None or plan['action'] == 'delete':
            continue
        else:
            key = plan['current']['uuid']
        keys.append((index, key))
    layout.sort(key=lambda pair: pair[1])

    wanted = [key for key, dummy in layout]
    kept = set(key for dummy, key in keys)
    slots = [n for n, key in enumerate(wanted) if key in kept]
    positions = [position for dummy, position in layout]
    taken = [positions[n] for n in slots]
    if any(a >= b for a, b in zip(taken, taken[1:])):
        positions = list(range(1, len(layout) + 1))
    for n, (dummy, key) in zip(slots, keys):
        wanted[n] = key
    now = dict(layout)
    target = dict(zip(wanted, positions))
    moves = [key for key in wanted if target[key] != now[key]]

    if moves and not module.check_mode:
        try:
            client.post('/api/%s/actions/reorder' % collection, {collection: [
                {'uuid': key, 'viewPosition': target[key]} for key in moves]})
        except RemnawaveApiError as exc:
            return exc

    for index, key in keys:
        if target[key] == now[key]:
            continue
        result = results[index]
        if result.get(item) and not module.check_mode:
            result[item] = dict(result[item], viewPosition=target[key])
        if plans[index]['action'] == 'create':
            continue
        result['changed'] = True
        if plans[index]['action'] == 'none':
            result['action'] = 'update'
        if module._diff:
            diff = result.get('diff') or dict(before={}, after={})
            result['diff'] = dict(
                before=dict(diff['before'], viewPosition=now[key]),
                after=dict(diff['after'], viewPosition=target[key]))
    return None
