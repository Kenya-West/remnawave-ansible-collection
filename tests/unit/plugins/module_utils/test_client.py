# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the HTTP client's caching of listings, its concurrent
reads, its request trace and its errors."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import io
import json
import threading
import time
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

    def test_prefetch_fills_the_cache(self):
        self.client.prefetch(['/api/hosts', '/api/nodes'])
        self.client.get('/api/hosts', cached=True)
        self.client.get('/api/nodes', cached=True)
        self.assertEqual(len(self.gets()), 2)

    def test_prefetch_skips_what_is_cached(self):
        self.client.get('/api/hosts', cached=True)
        self.client.prefetch(['/api/hosts', '/api/nodes'])
        self.assertEqual(sorted(c[1] for c in self.gets()),
                         ['https://panel.example.com/api/hosts',
                          'https://panel.example.com/api/nodes'])

    def test_requests_are_traced(self):
        self.client.get('/api/hosts')
        self.client.patch('/api/hosts', {'uuid': 'x'})
        self.assertEqual([(t['method'], t['path'], t['status'])
                          for t in self.client.trace],
                         [('GET', '/api/hosts', 200), ('PATCH', '/api/hosts', 200)])


class SlowTransport(object):
    """fetch_url taking a while per request, tracking how many overlap."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.most = 0

    def __call__(self, module, url, data=None, headers=None, method=None,
                 timeout=None):
        with self.lock:
            self.active += 1
            self.most = max(self.most, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1
        return io.BytesIO(json.dumps({'response': url}).encode()), {'status': 200}


class TestConcurrency(unittest.TestCase):

    def setUp(self):
        self.transport = SlowTransport()
        self.original = client_module.fetch_url
        client_module.fetch_url = self.transport
        self.client = RemnawaveClient(FakeModule())

    def tearDown(self):
        client_module.fetch_url = self.original

    def test_prefetch_reads_listings_at_the_same_time(self):
        self.client.prefetch(['/api/hosts', '/api/nodes', '/api/config-profiles'])
        self.assertEqual(self.transport.most, 3)
        self.assertEqual(self.client.get('/api/nodes', cached=True),
                         'https://panel.example.com/api/nodes')

    def test_run_parallel_keeps_to_its_workers_and_the_order(self):
        calls = [lambda i=i: (self.client.get('/api/%d' % i), i)[1]
                 for i in range(6)]
        self.assertEqual(self.client.run_parallel(calls, 2), list(range(6)))
        self.assertEqual(self.transport.most, 2)

    def test_run_parallel_returns_exceptions_in_place(self):
        def fail():
            raise RemnawaveApiError('rejected', status=400)
        results = self.client.run_parallel([lambda: 1, fail, lambda: 3], 4)
        self.assertEqual(results[0], 1)
        self.assertIsInstance(results[1], RemnawaveApiError)
        self.assertEqual(results[2], 3)


class TracingModule(FakeModule):
    """A module run at -vvv, keeping what it would exit with."""

    _verbosity = 3

    def exit_json(self, **kwargs):
        self.exited = kwargs

    def fail_json(self, msg, **kwargs):
        self.failed = dict(kwargs, msg=msg)


class TestTraceReport(unittest.TestCase):

    def setUp(self):
        self.original = client_module.fetch_url
        client_module.fetch_url = RecordingTransport()

    def tearDown(self):
        client_module.fetch_url = self.original

    def test_results_carry_the_trace_at_vvv(self):
        module = TracingModule()
        client = RemnawaveClient(module)
        client.get('/api/hosts')
        module.exit_json(changed=False)
        self.assertEqual(module.exited['changed'], False)
        self.assertEqual([t['path'] for t in module.exited['api_trace']],
                         ['/api/hosts'])
        self.assertIn('api_seconds', module.exited)

    def test_failures_carry_it_too(self):
        module = TracingModule()
        RemnawaveClient(module)
        module.fail_json('broken')
        self.assertEqual(module.failed['msg'], 'broken')
        self.assertEqual(module.failed['api_trace'], [])

    def test_no_trace_below_vvv(self):
        module = FakeModule()
        RemnawaveClient(module)
        self.assertFalse(hasattr(module, 'exit_json'))


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
