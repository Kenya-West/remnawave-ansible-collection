# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Planning and applying the desired state of infra billing providers.

Shared by the infra_provider module, which manages one provider per task,
and the infra_providers module, which manages many in a single task. As
for nodes, planning only reads the panel and applying only writes to it.

A provider is where nodes are hosted; nodes refer to it through their
``providerUuid``, which the node modules manage as ``provider``. Deleting
a provider makes the panel unset that reference on its nodes and delete
its billing history and billed nodes along with it, so a deletion's diff
shows all three.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible_collections.kenyawest.remnawave.plugins.module_utils.batch import (
    DEFAULT_PARALLELISM, collect_outcomes,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    FieldSpec, build_patch, is_uuid,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_infra_provider, list_infra_providers, list_nodes,
)


PROVIDERS_PATH = '/api/infra-billing/providers'

# The panel's limits for a provider name.
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 30

FIELDS = [
    # An empty string clears either link; the panel stores null.
    FieldSpec('favicon_link', 'faviconLink', to_api=lambda v: v or None),
    FieldSpec('login_url', 'loginUrl', to_api=lambda v: v or None),
]


def infra_provider_options():
    """The options describing one provider, without the connection options."""
    return dict(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        favicon_link=dict(type='str'),
        login_url=dict(type='str'),
    )


def infra_provider_listings(entries):
    """The panel listings that planning these provider entries reads."""
    paths = [PROVIDERS_PATH]
    if any(e['state'] == 'absent' for e in entries):
        # To show which nodes a deletion unlinks.
        paths.append('/api/nodes')
    return paths


def validate_name(name):
    if not MIN_NAME_LENGTH <= len(name) <= MAX_NAME_LENGTH:
        raise ValueError('Infra provider name %r must be %d to %d characters long'
                         % (name, MIN_NAME_LENGTH, MAX_NAME_LENGTH))


def deletion_before(client, current):
    """What deleting a provider takes with it, for the diff."""
    before = dict(name=current['name'], nodes=sorted(
        n.get('name') for n in list_nodes(client)
        if n.get('providerUuid') == current['uuid']))
    history = current.get('billingHistory') or {}
    if history.get('totalBills'):
        before['billingHistory'] = history
    billed = [b.get('name') or (b.get('details') or {}).get('nodeUuid')
              for b in current.get('billingNodes') or []]
    if billed:
        before['billingNodes'] = sorted(str(b) for b in billed)
    return before


def plan_infra_provider(module, client, params):
    """Work out what one provider needs, without changing anything.

    Returns a dict with the ``action`` to take (``create``, ``update``,
    ``delete`` or ``none``), the provider as found (``current``), the
    request ``payload`` and the ``before``/``after`` diff.
    """
    name = params['name']
    current = find_infra_provider(client, name)
    plan = dict(name=name, current=current, action='none', payload=None,
                before={}, after={})

    if params['state'] == 'absent':
        if current is not None:
            plan.update(action='delete',
                        before=deletion_before(client, current))
        return plan

    patch, before, after = build_patch(params, current, FIELDS)
    plan.update(before=before, after=after)

    if current is None:
        if is_uuid(name):
            raise ValueError('Infra provider %r not found; a provider is '
                             'created by name, not by UUID' % name)
        validate_name(name)
        # The create body takes no nulls: a cleared link is just left out.
        payload = dict((k, v) for k, v in patch.items() if v is not None)
        payload['name'] = name
        after['name'] = name
        plan.update(action='create', payload=payload)
    elif patch:
        payload = dict(patch)
        payload['uuid'] = current['uuid']
        plan.update(action='update', payload=payload)
    return plan


def infra_provider_result(module, plan, provider):
    changed = plan['action'] != 'none'
    result = dict(changed=changed)
    if provider is not None:
        result['provider'] = provider
    if changed and module._diff:
        result['diff'] = dict(before=plan['before'], after=plan['after'])
    return result


def write_plan(client, plan):
    """The one write a plan takes; returns the provider it leaves, if any."""
    if plan['action'] == 'delete':
        client.delete('%s/%s' % (PROVIDERS_PATH, plan['current']['uuid']))
        return None
    if plan['action'] == 'create':
        return client.post(PROVIDERS_PATH, plan['payload'])
    return client.patch(PROVIDERS_PATH, plan['payload'])


def apply_infra_provider_plan(module, client, plan):
    """Carry out a plan (only pretending in check mode)."""
    action = plan['action']
    if action == 'none':
        return infra_provider_result(module, plan, plan['current'])
    if module.check_mode:
        provider = None
        if action == 'create':
            provider = plan['payload']
        elif action == 'update':
            provider = dict(plan['current'], **plan['after'])
        return infra_provider_result(module, plan, provider)
    return infra_provider_result(module, plan, write_plan(client, plan))


def apply_infra_provider_plans(module, client, plans,
                               parallelism=DEFAULT_PARALLELISM):
    """Carry out the plans of a batch, ``parallelism`` writes at a time.

    Deletions go first, then updates and creations together: each provider
    takes exactly one write, independent of the others', and names are
    unique, so nothing else orders them. The panel has no bulk endpoints
    and no order for providers.

    Returns ``(results, failure)`` as apply_node_plans does.
    """
    if module.check_mode:
        return [apply_infra_provider_plan(module, client, p) for p in plans], None

    done = {}

    def record(index, provider):
        done[index] = provider

    def step(test):
        indices = [i for i, p in enumerate(plans) if test(p['action'])]
        outcomes = client.run_parallel(
            [lambda p=plans[i]: [write_plan(client, p)] for i in indices],
            parallelism)
        return collect_outcomes(plans, [[i] for i in indices], outcomes, record)

    failure = (step(lambda a: a == 'delete')
               or step(lambda a: a in ('create', 'update')))

    results = [None] * len(plans)
    for index, plan in enumerate(plans):
        if plan['action'] == 'none':
            results[index] = infra_provider_result(module, plan, plan['current'])
        elif index in done:
            results[index] = infra_provider_result(module, plan, done[index])
    return results, failure


def refresh_infra_providers(client, results):
    """Report the providers of ``results`` as the panel now holds them.

    The listing carries the billing summary that write answers may lack,
    so after a batch has written anything it is read again, once.
    """
    fresh = dict((p['uuid'], p) for p in list_infra_providers(client))
    for result in results:
        provider = (result or {}).get('provider')
        if provider and provider.get('uuid') in fresh:
            result['provider'] = fresh[provider['uuid']]


def entry_label(index, entry):
    return 'providers[%d] (%r)' % (index, entry.get('name'))


def plan_infra_providers(module, client, entries):
    """Plan every entry of a batch; raises over the first bad one.

    Each provider may be declared only once, and raised errors name the
    offending entry.
    """
    client.prefetch(infra_provider_listings(entries))
    plans = []
    claimed = {}
    for index, entry in enumerate(entries):
        label = entry_label(index, entry)
        try:
            plan = plan_infra_provider(module, client, entry)
        except RemnawaveApiError as exc:
            raise RemnawaveApiError('%s: %s' % (label, exc), status=exc.status,
                                    error_code=exc.error_code, body=exc.body)
        except ValueError as exc:
            raise ValueError('%s: %s' % (label, exc))
        # A provider addressed by UUID and by name is still one provider.
        key = (plan['current'] or {}).get('uuid') or plan['name']
        if key in claimed:
            raise ValueError('%s and %s address the same infra provider; '
                             'declare each provider once' % (claimed[key], label))
        claimed[key] = label
        plan['label'] = label
        plans.append(plan)
    return plans
