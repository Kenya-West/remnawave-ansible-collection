# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for resolving inbound tags to inbounds and config profiles."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_inbound, find_inbounds, inbound_view, resolve_inbound_uuids,
)


EU_UUID = '11111111-1111-1111-1111-111111111111'
US_UUID = '22222222-2222-2222-2222-222222222222'
VLESS_UUID = '33333333-3333-3333-3333-333333333333'
TROJAN_UUID = '44444444-4444-4444-4444-444444444444'
SS_UUID = '55555555-5555-5555-5555-555555555555'


class FakeClient(object):
    """Serves canned GET responses to the resource helpers."""

    def __init__(self, profiles):
        self.profiles = profiles

    def get(self, path, query=None, allow_404=False, cached=False):
        assert path == '/api/config-profiles'
        return {'configProfiles': self.profiles}


def profiles():
    return [
        {'uuid': EU_UUID, 'name': 'eu', 'inbounds': [
            {'uuid': VLESS_UUID, 'profileUuid': EU_UUID, 'tag': 'vless'},
            {'uuid': TROJAN_UUID, 'profileUuid': EU_UUID, 'tag': 'trojan'},
        ]},
        {'uuid': US_UUID, 'name': 'us', 'inbounds': [
            {'uuid': SS_UUID, 'profileUuid': US_UUID, 'tag': 'ss'},
        ]},
    ]


class TestFindInbound(unittest.TestCase):

    def test_by_tag_returns_the_inbound_and_its_profile(self):
        profile, inbound = find_inbound(FakeClient(profiles()), 'trojan')
        self.assertEqual(profile['name'], 'eu')
        self.assertEqual(inbound['uuid'], TROJAN_UUID)

    def test_by_uuid(self):
        profile, inbound = find_inbound(FakeClient(profiles()), SS_UUID)
        self.assertEqual((profile['name'], inbound['tag']), ('us', 'ss'))

    def test_missing_is_none_unless_required(self):
        client = FakeClient(profiles())
        self.assertEqual(find_inbound(client, 'nowhere'), (None, None))
        with self.assertRaises(RemnawaveApiError) as caught:
            find_inbound(client, 'nowhere', required=True)
        self.assertIn('available tags: ss, trojan, vless', str(caught.exception))

    def test_ambiguous_tag_is_an_error(self):
        data = profiles()
        data[1]['inbounds'].append({'uuid': 'x', 'tag': 'vless'})
        client = FakeClient(data)
        self.assertEqual(len(find_inbounds(client, 'vless')), 2)
        with self.assertRaises(RemnawaveApiError) as caught:
            find_inbound(client, 'vless')
        self.assertIn("several config profiles ('eu', 'us')", str(caught.exception))


class TestInboundView(unittest.TestCase):

    def test_adds_the_profile_identity(self):
        profile = {'uuid': EU_UUID, 'name': 'eu'}
        view = inbound_view(profile, {'uuid': VLESS_UUID, 'tag': 'vless'})
        self.assertEqual(view['profileUuid'], EU_UUID)
        self.assertEqual(view['profileName'], 'eu')


class TestResolveInboundUuids(unittest.TestCase):

    def test_profile_is_derived_from_the_inbounds(self):
        result = resolve_inbound_uuids(
            FakeClient(profiles()), None, ['vless', TROJAN_UUID])
        self.assertEqual(result, (EU_UUID, [VLESS_UUID, TROJAN_UUID]))

    def test_inbounds_of_different_profiles_are_refused(self):
        with self.assertRaises(ValueError) as caught:
            resolve_inbound_uuids(FakeClient(profiles()), None, ['vless', 'ss'])
        self.assertIn("different config profiles ('eu', 'us')", str(caught.exception))

    def test_empty_inbounds_cannot_name_a_profile(self):
        with self.assertRaises(ValueError):
            resolve_inbound_uuids(FakeClient(profiles()), None, [])

    def test_unknown_tag_without_profile_is_not_found(self):
        with self.assertRaises(RemnawaveApiError):
            resolve_inbound_uuids(FakeClient(profiles()), None, ['nowhere'])

    def test_named_profile_must_hold_the_inbound(self):
        client = FakeClient(profiles())
        self.assertEqual(resolve_inbound_uuids(client, 'us', ['ss']),
                         (US_UUID, [SS_UUID]))
        with self.assertRaises(RemnawaveApiError):
            resolve_inbound_uuids(client, 'us', ['vless'])


if __name__ == '__main__':
    unittest.main()
