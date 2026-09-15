# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the HTTP client's caching of listings and its errors."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import io
import json
import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils import client as client_module
from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError, RemnawaveClient,
)


class FakeModule(object):

    params = {
        'panel_url': 'https://panel.example.com/',
        'token': 'token',
        'api_key': None,
        'timeout': 30,
        'request_headers': {},
    }


class RecordingTransport(object):
    """Stands in for fetch_url, recording every request it is given."""

    def __init__(self):
        self.calls = []

    def __call__(self, module, url, data=None, headers=None, method=None,
                 timeout=None):
        self.calls.append((method, url))
        body = json.dumps({'response': [{'n': len(self.calls)}]}).encode()
        return io.BytesIO(body), {'status': 200}


class TestListingCache(unittest.TestCase):

    def setUp(self):
        self.transport = RecordingTransport()
        self.original = client_module.fetch_url
        client_module.fetch_url = self.transport
        self.client = RemnawaveClient(FakeModule())

    def tearDown(self):
        client_module.fetch_url = self.original

    def gets(self):
        return [c for c in self.transport.calls if c[0] == 'GET']

    def test_cached_listing_is_fetched_once(self):
        first = self.client.get('/api/hosts', cached=True)
        second = self.client.get('/api/hosts', cached=True)
        self.assertEqual(first, second)
        self.assertEqual(len(self.gets()), 1)

    def test_uncached_reads_always_fetch(self):
        self.client.get('/api/hosts', cached=True)
        self.client.get('/api/hosts')
        self.client.get('/api/hosts')
        self.assertEqual(len(self.gets()), 3)

    def test_paths_are_cached_separately(self):
        self.client.get('/api/hosts', cached=True)
        self.client.get('/api/nodes', cached=True)
        self.assertEqual(len(self.gets()), 2)

    def test_queries_are_never_cached(self):
        self.client.get('/api/users', query={'size': 1}, cached=True)
        self.client.get('/api/users', query={'size': 1}, cached=True)
        self.assertEqual(len(self.gets()), 2)

    def test_a_write_drops_the_cache(self):
        self.client.get('/api/hosts', cached=True)
        self.client.patch('/api/hosts', {'uuid': 'x'})
        self.client.get('/api/hosts', cached=True)
        self.assertEqual(len(self.gets()), 2)


def failing_transport(module, url, data=None, headers=None, method=None,
                      timeout=None):
    """fetch_url on an HTTP error: the exception comes back as the response,
    already read out, and its body is in the info dict instead."""
    body = json.dumps({'message': "Config doesn't have outbounds.",
                       'errorCode': 'A061'}).encode()
    return io.BytesIO(b''), {'status': 500, 'body': body,
                             'msg': 'HTTP Error 500: Internal Server Error'}


class TestErrors(unittest.TestCase):

    def setUp(self):
        self.original = client_module.fetch_url
        client_module.fetch_url = failing_transport

    def tearDown(self):
        client_module.fetch_url = self.original

    def test_the_panel_message_is_reported(self):
        with self.assertRaises(RemnawaveApiError) as caught:
            RemnawaveClient(FakeModule()).patch('/api/config-profiles', {'uuid': 'x'})
        self.assertIn("Config doesn't have outbounds.", str(caught.exception))
        self.assertEqual(caught.exception.status, 500)
        self.assertEqual(caught.exception.error_code, 'A061')


if __name__ == '__main__':
    unittest.main()
