# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for planning host changes, alone and in batches."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.host import (
    host_options, plan_host, plan_hosts, to_route_id,
)


PROFILE_UUID = '11111111-1111-1111-1111-111111111111'
INBOUND_UUID = '22222222-2222-2222-2222-222222222222'
NODE_UUID = '33333333-3333-3333-3333-333333333333'
HOST_UUID = '44444444-4444-4444-4444-444444444444'


class FakeModule(object):
    check_mode = False
    _diff = False


class CountingClient(object):
    """Serves canned listings, caching them as the real client does, and
    counts how often each path actually reaches the panel."""

    def __init__(self):
        self.reads = {}
        self.cache = {}
        self.responses = {
            '/api/hosts': [{
                'uuid': HOST_UUID, 'remark': 'Amsterdam',
                'address': 'ams.example.com', 'port': 443,
                'isDisabled': False, 'nodes': [NODE_UUID],
            }],
            '/api/nodes': [{'uuid': NODE_UUID, 'name': 'nl-ams-1'}],
            '/api/config-profiles': {'configProfiles': [{
                'uuid': PROFILE_UUID, 'name': 'default-profile',
                'inbounds': [{'uuid': INBOUND_UUID, 'tag': 'vless'}],
            }]},
        }

    def get(self, path, query=None, allow_404=False, cached=False):
        if cached and path in self.cache:
            return self.cache[path]
        self.reads[path] = self.reads.get(path, 0) + 1
        if cached:
            self.cache[path] = self.responses[path]
        return self.responses[path]


def entry(**options):
    """One host's options as AnsibleModule would hand them over."""
    params = dict((name, spec.get('default'))
                  for name, spec in host_options().items())
    params.update(options)
    return params


NEW_HOST = dict(config_profile='default-profile', inbound='vless',
                address='fra.example.com', port=443)


class TestToRouteId(unittest.TestCase):

    def test_empty_clears(self):
        self.assertIsNone(to_route_id(''))
        self.assertIsNone(to_route_id(None))

    def test_numbers_and_numeric_strings(self):
        self.assertEqual(to_route_id(400), 400)
        self.assertEqual(to_route_id('401'), 401)

    def test_out_of_range_and_bool_rejected(self):
        for value in (-1, 65536, True, 'four'):
            with self.assertRaises(ValueError):
                to_route_id(value)


class TestPlanHost(unittest.TestCase):

    def plan(self, **options):
        return plan_host(FakeModule(), CountingClient(), entry(**options))

    def test_unchanged_host_needs_nothing(self):
        plan = self.plan(remark='Amsterdam', port=443, nodes=['nl-ams-1'])
        self.assertEqual(plan['action'], 'none')

    def test_changed_field_is_an_update_of_just_that_field(self):
        plan = self.plan(remark='Amsterdam', port=8443, state='disabled')
        self.assertEqual(plan['action'], 'update')
        self.assertEqual(plan['payload'],
                         {'uuid': HOST_UUID, 'port': 8443, 'isDisabled': True})

    def test_missing_host_is_created_with_resolved_inbound(self):
        plan = self.plan(remark='Frankfurt', **NEW_HOST)
        self.assertEqual(plan['action'], 'create')
        self.assertEqual(plan['payload']['remark'], 'Frankfurt')
        self.assertEqual(plan['payload']['inbound'], {
            'configProfileUuid': PROFILE_UUID,
            'configProfileInboundUuid': INBOUND_UUID,
        })

    def test_creation_requires_the_inbound_and_address(self):
        with self.assertRaises(ValueError) as caught:
            self.plan(remark='Frankfurt', port=443)
        self.assertIn('config_profile, inbound, address', str(caught.exception))

    def test_absent_host_that_is_missing_needs_nothing(self):
        plan = self.plan(remark='Nowhere', state='absent')
        self.assertEqual(plan['action'], 'none')

    def test_absent_host_that_exists_is_deleted(self):
        plan = self.plan(identify_by='address', address='ams.example.com',
                         state='absent')
        self.assertEqual(plan['action'], 'delete')


class TestPlanHosts(unittest.TestCase):

    def test_listings_are_read_once_for_the_whole_batch(self):
        client = CountingClient()
        plans = plan_hosts(FakeModule(), client, [
            entry(remark='Amsterdam', nodes=['nl-ams-1']),
            entry(remark='Frankfurt', nodes=['nl-ams-1'], **NEW_HOST),
            entry(remark='Warsaw', state='absent'),
        ])
        self.assertEqual([p['action'] for p in plans], ['none', 'create', 'none'])
        self.assertEqual(client.reads, {'/api/hosts': 1, '/api/nodes': 1,
                                        '/api/config-profiles': 1})

    def test_errors_name_the_entry(self):
        with self.assertRaises(ValueError) as caught:
            plan_hosts(FakeModule(), CountingClient(), [
                entry(remark='Amsterdam'),
                entry(remark='Frankfurt', port=443),
            ])
        self.assertIn("hosts[1] (remark 'Frankfurt')", str(caught.exception))

    def test_unknown_reference_names_the_entry(self):
        with self.assertRaises(RemnawaveApiError) as caught:
            plan_hosts(FakeModule(), CountingClient(), [
                entry(remark='Amsterdam', nodes=['no-such-node']),
            ])
        self.assertIn('hosts[0]', str(caught.exception))

    def test_a_host_declared_twice_is_refused(self):
        # Once by remark, once by address: still the same host.
        with self.assertRaises(ValueError) as caught:
            plan_hosts(FakeModule(), CountingClient(), [
                entry(remark='Amsterdam', port=443),
                entry(identify_by='address', address='ams.example.com',
                      state='disabled'),
            ])
        self.assertIn('declare each host once', str(caught.exception))

    def test_a_new_host_declared_twice_is_refused(self):
        with self.assertRaises(ValueError):
            plan_hosts(FakeModule(), CountingClient(), [
                entry(remark='Frankfurt', **NEW_HOST),
                entry(remark='Frankfurt', **NEW_HOST),
            ])


if __name__ == '__main__':
    unittest.main()
