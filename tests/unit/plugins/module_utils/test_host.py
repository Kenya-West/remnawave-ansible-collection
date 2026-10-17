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
    apply_host_plans, arrange_hosts, host_listings, host_options, plan_host,
    plan_hosts, to_route_id,
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

    def prefetch(self, paths):
        for path in paths:
            self.get(path, cached=True)


class WritingClient(object):
    """Records the writes it is given, answering each like the panel does;
    a path in ``reject`` answers with that status instead."""

    def __init__(self, reject=None):
        self.writes = []
        self.reject = reject or {}

    def write(self, method, path, data):
        self.writes.append((method, path, data))
        if path in self.reject:
            raise RemnawaveApiError('rejected', status=self.reject[path])
        if path.startswith('/api/hosts/bulk/'):
            return None
        return dict(data, answered=True)

    def post(self, path, data=None):
        return self.write('POST', path, data)

    def patch(self, path, data=None):
        return self.write('PATCH', path, data)

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

    def test_inbound_tag_alone_names_its_config_profile(self):
        options = dict(NEW_HOST, config_profile=None)
        plan = self.plan(remark='Frankfurt', **options)
        self.assertEqual(plan['action'], 'create')
        self.assertEqual(plan['payload']['inbound'], {
            'configProfileUuid': PROFILE_UUID,
            'configProfileInboundUuid': INBOUND_UUID,
        })

    def test_config_profile_without_inbound_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.plan(remark='Amsterdam', config_profile='default-profile')
        self.assertIn('config_profile requires inbound', str(caught.exception))

    def test_creation_requires_the_inbound_and_address(self):
        with self.assertRaises(ValueError) as caught:
            self.plan(remark='Frankfurt', port=443)
        self.assertIn('inbound, address', str(caught.exception))

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


class TestHostListings(unittest.TestCase):

    def test_only_what_planning_reads(self):
        self.assertEqual(host_listings([entry(remark='a', state='absent',
                                              nodes=['n'])]),
                         ['/api/hosts'])
        self.assertEqual(host_listings([entry(remark='a', nodes=['n']),
                                        entry(remark='b', inbound='vless')]),
                         ['/api/hosts', '/api/nodes', '/api/config-profiles'])


def plan(action, uuid=None, label='hosts[0]', **payload):
    current = None if uuid is None else {'uuid': uuid, 'remark': label, 'port': 443}
    if uuid is not None and action == 'update':
        payload['uuid'] = uuid
    return dict(action=action, current=current, payload=payload or None,
                before={}, after={}, label=label)


class TestApplyHostPlans(unittest.TestCase):

    def test_writes_go_deletes_updates_creates_in_fewest_requests(self):
        client = WritingClient()
        plans = [
            plan('create', label='new-1', remark='new-1'),
            plan('update', 'u-1', port=8443),
            plan('delete', 'd-1'),
            plan('update', 'u-2', port=8443),
            plan('update', 'u-3', port=9443),
            plan('none', 'n-1'),
            plan('delete', 'd-2'),
            plan('create', label='new-2', remark='new-2'),
        ]
        results, failure = apply_host_plans(FakeModule(), client, plans, 4)
        self.assertIsNone(failure)
        self.assertEqual([(m, p) for m, p, d in client.writes], [
            ('POST', '/api/hosts/bulk/delete'),
            ('PATCH', '/api/hosts/bulk/update'),
            ('PATCH', '/api/hosts'),
            ('POST', '/api/hosts'),
            ('POST', '/api/hosts'),
        ])
        self.assertEqual(client.writes[0][2], {'uuids': ['d-1', 'd-2']})
        self.assertEqual(client.writes[1][2], {'uuids': ['u-1', 'u-2'], 'port': 8443})
        self.assertEqual([w[2]['remark'] for w in client.writes[3:]],
                         ['new-1', 'new-2'])
        self.assertEqual([r['changed'] for r in results],
                         [True, True, True, True, True, False, True, True])
        # A bulk update is answered with no content: the host as found,
        # with the change applied.
        self.assertEqual(results[1]['host'], {'uuid': 'u-1', 'remark': 'hosts[0]',
                                              'port': 8443})
        self.assertNotIn('host', results[2])

    def test_a_panel_without_bulk_update_gets_one_request_per_host(self):
        client = WritingClient(reject={'/api/hosts/bulk/update': 404})
        results, failure = apply_host_plans(FakeModule(), client, [
            plan('update', 'u-1', port=8443), plan('update', 'u-2', port=8443),
        ], 4)
        self.assertIsNone(failure)
        self.assertEqual([p for m, p, d in client.writes],
                         ['/api/hosts/bulk/update', '/api/hosts', '/api/hosts'])
        self.assertTrue(results[1]['host']['answered'])

    def test_a_rejected_update_stops_before_the_creations(self):
        client = WritingClient(reject={'/api/hosts': 400})
        plans = [plan('update', 'u-1', port=8443, label='hosts[0]'),
                 plan('update', 'u-2', port=9443, label='hosts[1]'),
                 plan('create', label='hosts[2]', remark='new')]
        results, failure = apply_host_plans(FakeModule(), client, plans, 4)
        failed, exc = failure
        self.assertEqual([p['label'] for p in failed], ['hosts[0]'])
        self.assertEqual(exc.status, 400)
        self.assertEqual(results, [None, None, None])
        self.assertNotIn(('POST', '/api/hosts'), [(m, p) for m, p, d in client.writes])

    def test_a_rejected_deletion_writes_nothing_more(self):
        client = WritingClient(reject={'/api/hosts/bulk/delete': 400})
        results, failure = apply_host_plans(FakeModule(), client, [
            plan('none', 'n-1'), plan('delete', 'd-1'),
            plan('update', 'u-1', port=8443),
        ], 4)
        self.assertEqual([p['current']['uuid'] for p in failure[0]], ['d-1'])
        self.assertEqual(len(client.writes), 1)
        self.assertEqual([r is None for r in results], [False, True, True])

    def test_check_mode_writes_nothing(self):
        module = FakeModule()
        module.check_mode = True
        client = WritingClient()
        results, failure = apply_host_plans(module, client, [
            plan('update', 'u-1', port=8443), plan('delete', 'd-1'),
            plan('create', remark='new'),
        ], 4)
        self.assertIsNone(failure)
        self.assertEqual(client.writes, [])
        self.assertEqual([r['changed'] for r in results], [True, True, True])

    def test_ordered_creations_all_go_out_even_past_a_rejected_one(self):
        client = PanelClient(reject_remarks=['bad'])
        plans = [plan('create', label='hosts[0]', remark='good-1'),
                 plan('create', label='hosts[1]', remark='bad'),
                 plan('create', label='hosts[2]', remark='good-2')]
        results, failure = apply_host_plans(FakeModule(), client, plans, 4,
                                            ordered=True)
        self.assertEqual([p['label'] for p in failure[0]], ['hosts[1]'])
        self.assertEqual([r is None for r in results], [False, True, False])
        self.assertEqual(len(client.writes), 3)


class PanelClient(WritingClient):
    """Answers creations as the panel does: with a uuid, and the next
    position of the panel's own sequence."""

    def __init__(self, reject=None, next_position=10, reject_remarks=()):
        super(PanelClient, self).__init__(reject)
        self.next_position = next_position
        self.reject_remarks = reject_remarks

    def write(self, method, path, data):
        if path == '/api/hosts' and method == 'POST':
            self.writes.append((method, path, data))
            if data['remark'] in self.reject_remarks:
                raise RemnawaveApiError('rejected', status=400)
            self.next_position += 1
            return dict(data, uuid='new-' + data['remark'],
                        viewPosition=self.next_position - 1)
        return super(PanelClient, self).write(method, path, data)

    def reorders(self):
        return [dict((h['uuid'], h['viewPosition']) for h in d['hosts'])
                for m, p, d in self.writes if p == '/api/hosts/actions/reorder']


def listed(*hosts):
    """A hosts listing out of (uuid, viewPosition) pairs."""
    return [{'uuid': uuid, 'remark': uuid, 'viewPosition': position}
            for uuid, position in hosts]


def kept(uuid, position, action='none'):
    """The plan of a listed host the batch keeps."""
    p = plan(action, uuid, label=uuid)
    p['current']['viewPosition'] = position
    return p


class TestArrangeHosts(unittest.TestCase):

    def arrange(self, plans, listing, client=None, module=None):
        module = module or FakeModule()
        client = client or PanelClient()
        results, failure = apply_host_plans(module, client, plans, 4,
                                            ordered=True)
        self.assertIsNone(failure)
        error = arrange_hosts(module, client, plans, results, listing)
        return client, results, error

    def test_hosts_already_in_order_need_no_request(self):
        client, results, error = self.arrange(
            [kept('a', 1), kept('b', 2)], listed(('a', 1), ('x', 2), ('b', 3)))
        self.assertIsNone(error)
        self.assertEqual(client.writes, [])
        self.assertEqual([r['changed'] for r in results], [False, False])

    def test_listed_hosts_trade_places_and_the_others_keep_theirs(self):
        module = FakeModule()
        module._diff = True
        client, results, error = self.arrange(
            [kept('c', 5), kept('a', 1), kept('b', 3, 'update')],
            listed(('a', 1), ('x', 2), ('b', 3), ('c', 5)), module=module)
        self.assertEqual(client.reorders(), [{'c': 1, 'a': 3, 'b': 5}])
        self.assertEqual([r['changed'] for r in results], [True] * 3)
        self.assertEqual(results[0]['action'], 'update')
        self.assertEqual(results[0]['host']['viewPosition'], 1)
        self.assertEqual(results[0]['diff'], dict(before={'viewPosition': 5},
                                                  after={'viewPosition': 1}))
        # A host updated anyway keeps its own action.
        self.assertNotIn('action', results[2])

    def test_new_hosts_are_created_then_put_in_place(self):
        client, results, error = self.arrange(
            [plan('create', label='n', remark='n'), kept('a', 1)],
            listed(('a', 1)), client=PanelClient(next_position=7))
        self.assertEqual([p for m, p, d in client.writes],
                         ['/api/hosts', '/api/hosts/actions/reorder'])
        self.assertEqual(client.reorders(), [{'new-n': 1, 'a': 7}])
        self.assertEqual(results[0]['host']['viewPosition'], 1)
        self.assertNotIn('action', results[0])
        self.assertEqual(results[1]['action'], 'update')

    def test_deleted_hosts_free_their_places(self):
        client, results, error = self.arrange(
            [kept('d', 1, 'delete'), kept('b', 3), kept('a', 2)],
            listed(('d', 1), ('a', 2), ('b', 3)))
        self.assertEqual(client.reorders(), [{'b': 2, 'a': 3}])

    def test_listed_hosts_sharing_a_place_renumber_everyone(self):
        client, results, error = self.arrange(
            [kept('b', 1), kept('a', 1)],
            listed(('a', 1), ('x', 1), ('b', 1)))
        self.assertEqual(client.reorders(), [{'x': 2, 'a': 3}])

    def test_unlisted_hosts_sharing_a_place_are_left_alone(self):
        client, results, error = self.arrange(
            [kept('a', 2)], listed(('x', 1), ('y', 1), ('a', 2)))
        self.assertEqual(client.writes, [])

    def test_check_mode_predicts_the_moves_and_writes_nothing(self):
        module = FakeModule()
        module.check_mode = True
        client, results, error = self.arrange(
            [plan('create', label='n', remark='n'), kept('a', 1)],
            listed(('a', 1)), module=module)
        self.assertEqual(client.writes, [])
        self.assertEqual(results[1]['action'], 'update')
        self.assertTrue(results[1]['changed'])

    def test_a_rejected_reorder_is_returned_and_changes_no_result(self):
        client, results, error = self.arrange(
            [kept('b', 2), kept('a', 1)], listed(('a', 1), ('b', 2)),
            client=PanelClient(reject={'/api/hosts/actions/reorder': 400}))
        self.assertEqual(error.status, 400)
        self.assertEqual([r['changed'] for r in results], [False, False])


if __name__ == '__main__':
    unittest.main()
