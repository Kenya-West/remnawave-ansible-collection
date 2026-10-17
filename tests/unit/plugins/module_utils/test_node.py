# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for planning node changes, alone and in batches."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.node import (
    apply_node_plans, arrange_nodes, node_listings, node_options, plan_node,
    plan_nodes,
)


PROFILE_UUID = '11111111-1111-1111-1111-111111111111'
INBOUND_UUID = '22222222-2222-2222-2222-222222222222'
AMS_UUID = '33333333-3333-3333-3333-333333333333'
FRA_UUID = '44444444-4444-4444-4444-444444444444'


class FakeModule(object):
    check_mode = False
    _diff = False


class FakeClient(object):
    """Serves canned listings, caching them as the real client does, and
    records the writes it is given, answering each like the panel does; a
    path in ``reject`` answers with that status instead."""

    def __init__(self, reject=None, reject_names=()):
        self.reads = {}
        self.cache = {}
        self.writes = []
        self.reject = reject or {}
        self.reject_names = reject_names
        self.next_position = 10
        self.responses = {
            '/api/nodes': [
                {'uuid': AMS_UUID, 'name': 'nl-ams-1', 'address': '203.0.113.10',
                 'port': 2222, 'isDisabled': False, 'tags': [], 'viewPosition': 1,
                 'configProfile': {'activeConfigProfileUuid': PROFILE_UUID,
                                   'activeInbounds': [{'uuid': INBOUND_UUID}]}},
                {'uuid': FRA_UUID, 'name': 'de-fra-1', 'address': '203.0.113.20',
                 'port': 2222, 'isDisabled': True, 'tags': [], 'viewPosition': 2,
                 'configProfile': {'activeConfigProfileUuid': PROFILE_UUID,
                                   'activeInbounds': [{'uuid': INBOUND_UUID}]}},
            ],
            '/api/config-profiles': {'configProfiles': [{
                'uuid': PROFILE_UUID, 'name': 'default-profile',
                'inbounds': [{'uuid': INBOUND_UUID, 'tag': 'vless'}],
            }]},
            '/api/hosts': [
                {'uuid': 'h-ams', 'remark': 'Amsterdam', 'isDisabled': False,
                 'nodes': [AMS_UUID]},
                {'uuid': 'h-both', 'remark': 'Both', 'isDisabled': False,
                 'nodes': [AMS_UUID, FRA_UUID]},
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
        if path in self.reject:
            raise RemnawaveApiError('rejected', status=self.reject[path])
        if method == 'POST' and path == '/api/nodes':
            if data['name'] in self.reject_names:
                raise RemnawaveApiError('rejected', status=400)
            self.next_position += 1
            return dict(data, uuid='new-' + data['name'],
                        viewPosition=self.next_position - 1)
        if '/bulk' in path or method == 'DELETE':
            return None
        return dict(data or {}, answered=path)

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

    def paths(self):
        return [(m, p) for m, p, d in self.writes]


def entry(**options):
    """One node's options as AnsibleModule would hand them over."""
    params = dict((name, spec.get('default'))
                  for name, spec in node_options().items())
    params.update(options)
    return params


NEW_NODE = dict(address='198.51.100.1', port=2222, inbounds=['vless'])


class TestPlanNode(unittest.TestCase):

    def plan(self, **options):
        return plan_node(FakeModule(), FakeClient(), entry(**options))

    def test_unchanged_node_needs_nothing(self):
        plan = self.plan(name='nl-ams-1', address='203.0.113.10', inbounds=['vless'])
        self.assertEqual(plan['action'], 'none')

    def test_changed_field_is_an_update_of_just_that_field(self):
        plan = self.plan(name='nl-ams-1', port=3333, inbounds=['vless'])
        self.assertEqual(plan['action'], 'update')
        self.assertEqual(plan['payload'], {'port': 3333, 'uuid': AMS_UUID})

    def test_switching_enabled_is_an_update_without_payload(self):
        plan = self.plan(name='nl-ams-1', state='disabled')
        self.assertEqual((plan['action'], plan['enable'], plan['payload']),
                         ('update', False, None))

    def test_missing_node_is_created_and_disabled_when_wanted(self):
        plan = self.plan(name='new', state='disabled', **NEW_NODE)
        self.assertEqual(plan['action'], 'create')
        self.assertIs(plan['enable'], False)
        self.assertEqual(plan['payload']['configProfile'], {
            'activeConfigProfileUuid': PROFILE_UUID,
            'activeInbounds': [INBOUND_UUID]})

    def test_creation_requires_the_address_and_inbounds(self):
        with self.assertRaisesRegex(ValueError, 'requires: address, inbounds'):
            self.plan(name='new', port=2222)

    def test_config_profile_without_inbounds_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'config_profile requires inbounds'):
            self.plan(name='nl-ams-1', config_profile='default-profile')

    def test_absent_node_that_is_missing_needs_nothing(self):
        plan = self.plan(name='gone', state='absent', linked_hosts='delete')
        self.assertEqual((plan['action'], plan['cascade']), ('none', None))

    def test_absent_node_takes_its_linked_hosts_along(self):
        plan = self.plan(name='nl-ams-1', state='absent', linked_hosts='disable')
        self.assertEqual(plan['action'], 'delete')
        self.assertEqual([h['uuid'] for h in plan['cascade']['hosts']],
                         ['h-ams', 'h-both'])


class TestPlanNodes(unittest.TestCase):

    def test_listings_are_read_once_for_the_whole_batch(self):
        client = FakeClient()
        plan_nodes(FakeModule(), client, [
            entry(name='nl-ams-1', inbounds=['vless']),
            entry(name='de-fra-1', inbounds=['vless'], linked_hosts='enable'),
            entry(name='new', **NEW_NODE),
        ])
        self.assertEqual(client.reads, {'/api/nodes': 1, '/api/config-profiles': 1,
                                        '/api/hosts': 1})

    def test_a_node_declared_twice_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'declare each node once'):
            plan_nodes(FakeModule(), FakeClient(), [
                entry(name='nl-ams-1'), entry(name='nl-ams-1', port=1)])

    def test_errors_name_the_entry(self):
        with self.assertRaisesRegex(ValueError, r"nodes\[1\] \('new'\)"):
            plan_nodes(FakeModule(), FakeClient(), [
                entry(name='nl-ams-1'), entry(name='new')])

    def test_one_host_given_two_linked_hosts_actions_is_refused(self):
        with self.assertRaisesRegex(ValueError, "'Both'.*only one linked_hosts"):
            plan_nodes(FakeModule(), FakeClient(), [
                entry(name='nl-ams-1', linked_hosts='delete'),
                entry(name='de-fra-1', state='absent', linked_hosts='disable')])

    def test_listings_only_what_planning_reads(self):
        self.assertEqual(node_listings([entry(name='a', state='absent')]),
                         ['/api/nodes'])


class TestApplyNodePlans(unittest.TestCase):

    def apply(self, entries, client=None, module=None, ordered=False):
        module = module or FakeModule()
        client = client or FakeClient()
        plans = plan_nodes(module, client, [entry(**e) for e in entries])
        results, failure = apply_node_plans(module, client, plans, 4, ordered)
        return client, plans, results, failure

    def test_writes_go_in_steps_with_fewest_requests(self):
        client, plans, results, failure = self.apply([
            dict(name='new-1', state='disabled', **NEW_NODE),
            dict(name='nl-ams-1', state='absent', linked_hosts='disable'),
            dict(name='de-fra-1', state='enabled', tags=['A'], port=3333),
            dict(name='new-2', state='disabled', **NEW_NODE),
        ])
        self.assertIsNone(failure)
        self.assertEqual(client.paths(), [
            ('POST', '/api/hosts/bulk/disable'),
            ('DELETE', '/api/nodes/%s' % AMS_UUID),
            ('POST', '/api/nodes/bulk-actions'),
            ('PATCH', '/api/nodes'),
            ('POST', '/api/nodes'),
            ('POST', '/api/nodes'),
            ('POST', '/api/nodes/bulk-actions'),
        ])
        self.assertEqual(client.writes[2][2], {'uuids': [FRA_UUID], 'action': 'ENABLE'})
        self.assertEqual(client.writes[6][2], {'uuids': ['new-new-1', 'new-new-2'],
                                               'action': 'DISABLE'})
        self.assertEqual([r['changed'] for r in results], [True] * 4)
        self.assertEqual(results[1]['linked_hosts'], ['Amsterdam', 'Both'])
        self.assertNotIn('node', results[1])
        self.assertEqual(results[0]['node']['uuid'], 'new-new-1')

    def test_the_same_bulk_field_change_shares_one_request(self):
        client, plans, results, failure = self.apply([
            dict(name='nl-ams-1', tags=['PROD'], country_code='nl'),
            dict(name='de-fra-1', tags=['PROD'], country_code='NL'),
        ])
        self.assertEqual(client.writes, [('POST', '/api/nodes/bulk-actions/update', {
            'uuids': [AMS_UUID, FRA_UUID],
            'fields': {'tags': ['PROD'], 'countryCode': 'NL'}})])
        self.assertEqual([r['changed'] for r in results], [True, True])

    def test_the_same_profile_change_shares_one_request(self):
        client = FakeClient()
        for node in client.responses['/api/nodes']:
            node['configProfile'] = {}
        client, plans, results, failure = self.apply([
            dict(name='nl-ams-1', inbounds=['vless']),
            dict(name='de-fra-1', inbounds=['vless'])], client=client)
        self.assertEqual(client.paths(),
                         [('POST', '/api/nodes/bulk-actions/profile-modification')])

    def test_fields_without_a_bulk_request_go_one_per_node(self):
        client, plans, results, failure = self.apply([
            dict(name='nl-ams-1', port=3333), dict(name='de-fra-1', port=3333)])
        self.assertEqual(client.paths(), [('PATCH', '/api/nodes')] * 2)

    def test_a_panel_without_bulk_requests_gets_one_per_node(self):
        client = FakeClient(reject={'/api/nodes/bulk-actions/update': 404,
                                    '/api/nodes/bulk-actions': 404})
        client, plans, results, failure = self.apply([
            dict(name='nl-ams-1', tags=['A'], state='disabled'),
            dict(name='de-fra-1', tags=['A'])], client=client)
        self.assertIsNone(failure)
        self.assertEqual(client.paths(), [
            ('POST', '/api/nodes/bulk-actions'),
            ('POST', '/api/nodes/%s/actions/disable' % AMS_UUID),
            ('POST', '/api/nodes/bulk-actions/update'),
            ('PATCH', '/api/nodes'), ('PATCH', '/api/nodes'),
        ])

    def test_a_rejected_step_stops_the_later_ones(self):
        client, plans, results, failure = self.apply([
            dict(name='nl-ams-1', state='disabled', port=3333),
            dict(name='new', **NEW_NODE),
        ], client=FakeClient(reject={'/api/nodes': 400}))
        self.assertEqual([p['label'] for p in failure[0]], ["nodes[0] ('nl-ams-1')"])
        # The node was disabled but not updated: not carried out in full.
        self.assertEqual(results, [None, None])
        self.assertNotIn(('POST', '/api/nodes'), client.paths())

    def test_unordered_creations_stop_at_the_first_rejected(self):
        client, plans, results, failure = self.apply([
            dict(name='bad', **NEW_NODE), dict(name='good', **NEW_NODE),
        ], client=FakeClient(reject_names=['bad']))
        self.assertEqual(len(client.writes), 1)
        self.assertEqual(results, [None, None])

    def test_ordered_creations_all_go_out_and_are_put_in_place(self):
        client, plans, results, failure = self.apply([
            dict(name='new', **NEW_NODE), dict(name='de-fra-1'),
            dict(name='nl-ams-1'),
        ], ordered=True)
        self.assertIsNone(failure)
        listing = client.responses['/api/nodes']
        self.assertIsNone(arrange_nodes(FakeModule(), client, plans, results, listing))
        self.assertEqual(client.writes[-1][1:], ('/api/nodes/actions/reorder', {
            # de-fra-1 stays at 2, so it is not sent.
            'nodes': [{'uuid': 'new-new', 'viewPosition': 1},
                      {'uuid': AMS_UUID, 'viewPosition': 10}]}))
        self.assertEqual([r.get('action') for r in results], [None, None, 'update'])

    def test_check_mode_writes_nothing(self):
        module = FakeModule()
        module.check_mode = True
        client, plans, results, failure = self.apply([
            dict(name='nl-ams-1', port=3333),
            dict(name='de-fra-1', state='absent', linked_hosts='delete'),
            dict(name='new', **NEW_NODE)], module=module)
        self.assertEqual(client.writes, [])
        self.assertEqual([r['changed'] for r in results], [True, True, True])


if __name__ == '__main__':
    unittest.main()
