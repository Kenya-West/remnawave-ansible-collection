# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the desired/current comparison helpers.

Run with the collection on the Python path, for example:
    PYTHONPATH=/path/to/collections python3 -m unittest discover tests/unit
or via ansible-test units.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    FieldSpec, build_patch, desired_enabled, is_uuid, parse_traffic_limit,
    times_equal,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    hosts_linked_to_node,
)


class FakeClient(object):
    """Serves canned GET responses to the resource helpers."""

    def __init__(self, responses):
        self.responses = responses

    def get(self, path, query=None, allow_404=False):
        return self.responses[path]


NODE_UUID = '11111111-1111-1111-1111-111111111111'
OTHER_UUID = '22222222-2222-2222-2222-222222222222'


class TestParseTrafficLimit(unittest.TestCase):

    def test_integer_passthrough(self):
        self.assertEqual(parse_traffic_limit(1000), 1000)
        self.assertEqual(parse_traffic_limit(0), 0)

    def test_none(self):
        self.assertIsNone(parse_traffic_limit(None))

    def test_human_readable_binary_multiples(self):
        self.assertEqual(parse_traffic_limit('1K'), 1024)
        self.assertEqual(parse_traffic_limit('100GB'), 100 * 1024 ** 3)

    def test_bool_rejected(self):
        with self.assertRaises(ValueError):
            parse_traffic_limit(True)


class TestTimesEqual(unittest.TestCase):

    def test_equivalent_representations(self):
        self.assertTrue(times_equal('2027-01-01T00:00:00Z',
                                    '2027-01-01T00:00:00.000Z'))
        self.assertTrue(times_equal('2027-01-01T03:00:00+03:00',
                                    '2027-01-01T00:00:00Z'))

    def test_different_instants(self):
        self.assertFalse(times_equal('2027-01-01T00:00:00Z',
                                     '2027-01-02T00:00:00Z'))

    def test_unparseable_falls_back_to_string_compare(self):
        self.assertTrue(times_equal('never', 'never'))
        self.assertFalse(times_equal('never', 'sometime'))


class TestIsUuid(unittest.TestCase):

    def test_uuid(self):
        self.assertTrue(is_uuid('123e4567-e89b-12d3-a456-426614174000'))

    def test_not_uuid(self):
        self.assertFalse(is_uuid('alice'))
        self.assertFalse(is_uuid(None))
        self.assertFalse(is_uuid(42))


class TestDesiredEnabled(unittest.TestCase):

    def test_enabled_and_disabled_pin_the_status(self):
        self.assertTrue(desired_enabled('enabled'))
        self.assertFalse(desired_enabled('disabled'))

    def test_present_leaves_the_status_alone(self):
        self.assertIsNone(desired_enabled('present'))
        self.assertIsNone(desired_enabled('absent'))


class TestHostsLinkedToNode(unittest.TestCase):

    def client(self):
        return FakeClient({'/api/hosts': [
            {'remark': 'bound', 'nodes': [NODE_UUID]},
            {'remark': 'bound-among-others', 'nodes': [OTHER_UUID, NODE_UUID]},
            {'remark': 'other-node', 'nodes': [OTHER_UUID]},
            {'remark': 'unbound', 'nodes': []},
            {'remark': 'no-key'},
        ]})

    def test_only_hosts_bound_to_that_node(self):
        linked = hosts_linked_to_node(self.client(), NODE_UUID)
        self.assertEqual([h['remark'] for h in linked],
                         ['bound', 'bound-among-others'])

    def test_unbound_hosts_are_never_linked(self):
        # A host bound to no node is served from every node; a single node
        # going away must not disable it.
        linked = hosts_linked_to_node(self.client(), OTHER_UUID)
        self.assertNotIn('unbound', [h['remark'] for h in linked])
        self.assertNotIn('no-key', [h['remark'] for h in linked])


class TestBuildPatch(unittest.TestCase):

    FIELDS = [
        FieldSpec('status', 'status', to_api=lambda v: v.upper()),
        FieldSpec('expire_at', 'expireAt', kind='time'),
        FieldSpec('squads', 'activeSquads', kind='set'),
        FieldSpec('config', 'config', kind='json'),
    ]

    def test_no_change_when_equal(self):
        params = {'status': 'active',
                  'expire_at': '2027-01-01T00:00:00Z',
                  'squads': ['b', 'a'],
                  'config': {'x': 1}}
        current = {'status': 'ACTIVE',
                   'expireAt': '2027-01-01T00:00:00.000Z',
                   'activeSquads': ['a', 'b'],
                   'config': {'x': 1},
                   'serverOnlyField': 'ignored'}
        patch, before, after = build_patch(params, current, self.FIELDS)
        self.assertEqual(patch, {})

    def test_only_differing_fields_in_patch(self):
        params = {'status': 'disabled',
                  'expire_at': '2027-01-01T00:00:00Z',
                  'squads': None,
                  'config': None}
        current = {'status': 'ACTIVE',
                   'expireAt': '2027-01-01T00:00:00Z'}
        patch, before, after = build_patch(params, current, self.FIELDS)
        self.assertEqual(patch, {'status': 'DISABLED'})
        self.assertEqual(before, {'status': 'ACTIVE'})
        self.assertEqual(after, {'status': 'DISABLED'})

    def test_omitted_options_untouched(self):
        params = {'status': None, 'expire_at': None,
                  'squads': None, 'config': None}
        current = {'status': 'ACTIVE'}
        patch, dummy, dummy2 = build_patch(params, current, self.FIELDS)
        self.assertEqual(patch, {})

    def test_create_includes_all_set_options(self):
        params = {'status': 'active', 'expire_at': None,
                  'squads': ['a'], 'config': None}
        patch, dummy, dummy2 = build_patch(params, None, self.FIELDS)
        self.assertEqual(patch, {'status': 'ACTIVE', 'activeSquads': ['a']})


if __name__ == '__main__':
    unittest.main()
