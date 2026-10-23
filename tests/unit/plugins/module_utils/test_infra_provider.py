# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for planning infra provider changes, alone and in batches."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.infra_provider import (
    apply_infra_provider_plans, infra_provider_listings, infra_provider_options,
    plan_infra_provider, plan_infra_providers,
)


HETZNER_UUID = '11111111-1111-1111-1111-111111111111'
OVH_UUID = '22222222-2222-2222-2222-222222222222'
PROVIDERS = '/api/infra-billing/providers'


class FakeModule(object):
    check_mode = False
    _diff = False


class FakeClient(object):
    """Serves canned listings, caching them as the real client does, and
    records the writes it is given; a path in ``reject`` answers with that
    status instead."""

    def __init__(self, reject=None):
        self.reads = {}
        self.cache = {}
        self.writes = []
        self.reject = reject or {}
        self.responses = {
            PROVIDERS: {'total': 2, 'providers': [
                {'uuid': HETZNER_UUID, 'name': 'Hetzner',
                 'faviconLink': 'https://hetzner.example/icon.ico',
                 'loginUrl': 'https://console.hetzner.example',
                 'billingHistory': {'totalAmount': 30, 'totalBills': 2},
                 'billingNodes': [{'name': 'de-fsn-1', 'details': None}]},
                {'uuid': OVH_UUID, 'name': 'OVHcloud', 'faviconLink': None,
                 'loginUrl': None,
                 'billingHistory': {'totalAmount': 0, 'totalBills': 0},
                 'billingNodes': []},
            ]},
            '/api/nodes': [
                {'uuid': 'n-1', 'name': 'de-fsn-2', 'providerUuid': HETZNER_UUID},
                {'uuid': 'n-2', 'name': 'de-fsn-1', 'providerUuid': HETZNER_UUID},
                {'uuid': 'n-3', 'name': 'fr-gra-1', 'providerUuid': OVH_UUID},
            ],
        }

    def get(self, path, query=None, allow_404=False, cached=False):
        if cached and path in self.cache:
            return self.cache[path]
        self.reads[path] = self.reads.get(path, 0) + 1
        if cached:
            self.cache[path] = self.responses[path]
        return self.responses[path]

    def prefetch(self, paths):
        for path in paths:
            self.get(path, cached=True)

    def write(self, method, path, data):
        self.writes.append((method, path, data))
        if (method, path) in self.reject:
            raise RemnawaveApiError('rejected', status=self.reject[(method, path)])
        if method == 'DELETE':
            return {'isDeleted': True}
        if method == 'POST':
            return dict(data, uuid='new-' + data['name'])
        return dict(data, answered=True)

    def post(self, path, data=None):
        return self.write('POST', path, data)

    def patch(self, path, data=None):
        return self.write('PATCH', path, data)

    def delete(self, path):
        return self.write('DELETE', path, None)

    @staticmethod
    def run_parallel(calls, workers):
        results = []
        for call in calls:
            try:
                results.append(call())
            except Exception as exc:  # pylint: disable=broad-except
                results.append(exc)
        return results


def entry(**options):
    """One provider's options as AnsibleModule would hand them over."""
    params = dict((name, spec.get('default'))
                  for name, spec in infra_provider_options().items())
    params.update(options)
    return params


class TestPlanInfraProvider(unittest.TestCase):

    def plan(self, **options):
        return plan_infra_provider(FakeModule(), FakeClient(), entry(**options))

    def test_unchanged_provider_needs_nothing(self):
        plan = self.plan(name='Hetzner', login_url='https://console.hetzner.example')
        self.assertEqual(plan['action'], 'none')

    def test_changed_link_is_an_update_of_just_that_link(self):
        plan = self.plan(name='Hetzner', login_url='https://new.example')
        self.assertEqual(plan['payload'], {'loginUrl': 'https://new.example',
                                           'uuid': HETZNER_UUID})

    def test_an_empty_link_clears_it(self):
        plan = self.plan(name='Hetzner', favicon_link='')
        self.assertEqual(plan['payload'], {'faviconLink': None, 'uuid': HETZNER_UUID})
        self.assertEqual(self.plan(name='OVHcloud', favicon_link='')['action'], 'none')

    def test_creation_leaves_cleared_links_out(self):
        plan = self.plan(name='Vultr', favicon_link='', login_url='https://v.example')
        self.assertEqual(plan['action'], 'create')
        self.assertEqual(plan['payload'], {'name': 'Vultr',
                                           'loginUrl': 'https://v.example'})

    def test_a_name_the_panel_would_refuse_is_refused(self):
        with self.assertRaisesRegex(ValueError, '2 to 30 characters'):
            self.plan(name='X')
        with self.assertRaisesRegex(ValueError, '2 to 30 characters'):
            self.plan(name='X' * 31)

    def test_an_unknown_uuid_is_not_created(self):
        with self.assertRaisesRegex(ValueError, 'created by name'):
            self.plan(name='33333333-3333-3333-3333-333333333333')

    def test_deletion_shows_what_it_takes_along(self):
        plan = self.plan(name='Hetzner', state='absent')
        self.assertEqual(plan['action'], 'delete')
        self.assertEqual(plan['before'], {
            'name': 'Hetzner', 'nodes': ['de-fsn-1', 'de-fsn-2'],
            'billingHistory': {'totalAmount': 30, 'totalBills': 2},
            'billingNodes': ['de-fsn-1']})

    def test_absent_provider_that_is_missing_needs_nothing(self):
        self.assertEqual(self.plan(name='Gone', state='absent')['action'], 'none')

    def test_listings_only_what_planning_reads(self):
        self.assertEqual(infra_provider_listings([entry(name='a')]), [PROVIDERS])
        self.assertEqual(infra_provider_listings([entry(name='a', state='absent')]),
                         [PROVIDERS, '/api/nodes'])


class TestPlanInfraProviders(unittest.TestCase):

    def test_listings_are_read_once_for_the_whole_batch(self):
        client = FakeClient()
        plan_infra_providers(FakeModule(), client, [
            entry(name='Hetzner', state='absent'), entry(name='OVHcloud'),
            entry(name='Vultr')])
        self.assertEqual(client.reads, {PROVIDERS: 1, '/api/nodes': 1})

    def test_a_provider_declared_by_name_and_uuid_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'declare each provider once'):
            plan_infra_providers(FakeModule(), FakeClient(), [
                entry(name='Hetzner'), entry(name=HETZNER_UUID, state='absent')])

    def test_errors_name_the_entry(self):
        with self.assertRaisesRegex(ValueError, r"providers\[1\] \('X'\)"):
            plan_infra_providers(FakeModule(), FakeClient(), [
                entry(name='Hetzner'), entry(name='X')])


class TestApplyInfraProviderPlans(unittest.TestCase):

    def apply(self, entries, client=None, module=None):
        module = module or FakeModule()
        client = client or FakeClient()
        plans = plan_infra_providers(module, client, [entry(**e) for e in entries])
        results, failure = apply_infra_provider_plans(module, client, plans, 4)
        return client, results, failure

    def test_deletions_go_before_updates_and_creations(self):
        client, results, failure = self.apply([
            dict(name='Vultr'),
            dict(name='OVHcloud', login_url='https://ovh.example'),
            dict(name='Hetzner', state='absent'),
            dict(name='Gone', state='absent'),
        ])
        self.assertIsNone(failure)
        self.assertEqual([(m, p) for m, p, d in client.writes], [
            ('DELETE', '%s/%s' % (PROVIDERS, HETZNER_UUID)),
            ('POST', PROVIDERS),
            ('PATCH', PROVIDERS),
        ])
        self.assertEqual([r['changed'] for r in results], [True, True, True, False])
        self.assertEqual(results[0]['provider']['uuid'], 'new-Vultr')
        self.assertNotIn('provider', results[2])

    def test_a_rejected_deletion_stops_the_later_writes(self):
        client = FakeClient(reject={('DELETE', '%s/%s' % (PROVIDERS, HETZNER_UUID)): 500})
        client, results, failure = self.apply([
            dict(name='Vultr'), dict(name='Hetzner', state='absent')], client=client)
        self.assertEqual(len(client.writes), 1)
        self.assertEqual(failure[0][0]['name'], 'Hetzner')
        self.assertEqual(results, [None, None])

    def test_check_mode_writes_nothing(self):
        module = FakeModule()
        module.check_mode = True
        client, results, failure = self.apply([
            dict(name='Vultr'), dict(name='OVHcloud', login_url='https://ovh.example'),
            dict(name='Hetzner', state='absent')], module=module)
        self.assertEqual(client.writes, [])
        self.assertEqual([r['changed'] for r in results], [True] * 3)
        self.assertEqual(results[1]['provider']['loginUrl'], 'https://ovh.example')


if __name__ == '__main__':
    unittest.main()
