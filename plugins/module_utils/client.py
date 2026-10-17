# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Thin HTTP client for the Remnawave panel API.

Everything Remnawave-HTTP-specific lives here: authentication headers,
the Caddy ``X-Api-Key`` protection header, JSON encoding/decoding, the
``{"response": ...}`` envelope, and error translation. Resource modules
never talk to ``fetch_url`` directly.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import threading
import time

from ansible.module_utils.common.text.converters import to_native, to_text
from ansible.module_utils.six.moves.urllib.parse import urlencode
from ansible.module_utils.urls import fetch_url


class RemnawaveApiError(Exception):
    """Raised for transport failures and non-2xx API responses."""

    def __init__(self, message, status=None, error_code=None, body=None):
        super(RemnawaveApiError, self).__init__(message)
        self.status = status
        self.error_code = error_code
        self.body = body


class RemnawaveClient(object):

    def __init__(self, module):
        self.module = module
        params = module.params
        self.base_url = params['panel_url'].rstrip('/')
        self.timeout = params['timeout']
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % params['token'],
        }
        if params.get('api_key'):
            # Caddy "security via custom path" setup, see
            # https://docs.rw/security/caddy-with-custom-path
            self.headers['X-Api-Key'] = params['api_key']
        for key, value in (params.get('request_headers') or {}).items():
            self.headers[to_native(key)] = to_native(value)
        # Listings read with cached=True, by path. One module run resolves
        # many names against the same listings, and a batch plans many
        # entities against them, so each is fetched once per run.
        self._cache = {}
        # Requests may come from several threads at once (prefetch,
        # run_parallel), so the cache and the trace are shared under a lock.
        self._lock = threading.Lock()
        self.trace = []
        if getattr(module, '_verbosity', 0) >= 3:
            self._report_trace_on_exit()

    def _report_trace_on_exit(self):
        """At -vvv, add every request made and its duration to the result.

        Wraps this module's exit_json/fail_json rather than every module's
        call sites, so all modules report it the same way.
        """
        def reporting(original):
            def report(*args, **kwargs):
                with self._lock:
                    trace = list(self.trace)
                kwargs.setdefault('api_trace', trace)
                kwargs.setdefault('api_seconds',
                                  round(sum(t['seconds'] for t in trace), 3))
                original(*args, **kwargs)
            return report

        for name in ('exit_json', 'fail_json'):
            setattr(self.module, name, reporting(getattr(self.module, name)))

    def request(self, method, path, query=None, data=None, ok_statuses=None):
        """Perform a request and return ``(status, parsed_json_or_None)``.

        ``ok_statuses`` is an optional iterable of extra HTTP statuses that
        must not raise (e.g. 404 when probing for existence).
        """
        if method != 'GET':
            # Any write may change what a cached listing holds.
            with self._lock:
                self._cache.clear()
        if not path.startswith('/'):
            path = '/' + path
        url = self.base_url + path
        if query:
            pairs = [(k, v) for k, v in sorted(query.items()) if v is not None]
            if pairs:
                url += '?' + urlencode(pairs)

        body = None
        if data is not None:
            body = json.dumps(data)

        started = time.monotonic()
        response, info = fetch_url(
            self.module, url, data=body, headers=self.headers,
            method=method, timeout=self.timeout,
        )

        status = info['status']
        raw = b''
        if response is not None:
            raw = response.read()
        with self._lock:
            self.trace.append(dict(method=method, path=path, status=status,
                                   seconds=round(time.monotonic() - started, 3)))
        # On an HTTP error fetch_url hands back the exception itself as the
        # response, its body already read out into info['body'].
        if not raw and info.get('body'):
            raw = info['body']

        parsed = None
        if raw:
            try:
                parsed = json.loads(to_text(raw, errors='surrogate_or_strict'))
            except ValueError:
                parsed = None

        if status == -1:
            raise RemnawaveApiError(
                'Cannot reach Remnawave panel at %s: %s' % (self.base_url, info.get('msg')),
                status=status)

        if 200 <= status < 300 or status in (ok_statuses or ()):
            return status, parsed

        message = None
        error_code = None
        if isinstance(parsed, dict):
            message = parsed.get('message')
            error_code = parsed.get('errorCode')
            if isinstance(message, list):
                message = '; '.join(to_native(m) for m in message)
        if not message:
            message = info.get('msg') or 'HTTP %s' % status
        raise RemnawaveApiError(
            'Remnawave API error on %s %s: %s' % (method, path, message),
            status=status, error_code=error_code, body=parsed)

    @staticmethod
    def _unwrap(parsed):
        if isinstance(parsed, dict) and 'response' in parsed:
            return parsed['response']
        return parsed

    def get(self, path, query=None, allow_404=False, cached=False):
        """GET ``path`` and unwrap the response.

        ``cached`` reuses the response of an earlier cached GET of the same
        path until the next write through this client. Callers must not
        modify what it returns.
        """
        cacheable = cached and not query
        if cacheable:
            with self._lock:
                if path in self._cache:
                    return self._cache[path]
        ok = (404,) if allow_404 else ()
        status, parsed = self.request('GET', path, query=query, ok_statuses=ok)
        result = None if status == 404 else self._unwrap(parsed)
        if cacheable:
            with self._lock:
                self._cache[path] = result
        return result

    def prefetch(self, paths):
        """Read several listings at once into the cache of cached GETs.

        Listings are independent of each other, and each read is a round
        trip to the panel, so reading them all concurrently costs one round
        trip instead of one per listing. Raises the first error met.
        """
        with self._lock:
            missing = [p for p in paths if p not in self._cache]
        for result in self.run_parallel(
                [lambda p=p: self.get(p, cached=True) for p in missing],
                len(missing)):
            if isinstance(result, Exception):
                raise result

    @staticmethod
    def run_parallel(calls, workers):
        """Run callables on up to ``workers`` threads.

        Returns their results in the order of ``calls``; a call that raised
        has the exception in its place instead, so the caller decides which
        failures matter.
        """
        results = [None] * len(calls)
        pending = list(enumerate(calls))
        pending.reverse()
        lock = threading.Lock()

        def work():
            while True:
                with lock:
                    if not pending:
                        return
                    index, call = pending.pop()
                try:
                    results[index] = call()
                except Exception as exc:  # pylint: disable=broad-except
                    results[index] = exc

        threads = [threading.Thread(target=work)
                   for dummy in range(min(max(workers, 1), len(calls)))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results

    def post(self, path, data=None, query=None):
        dummy, parsed = self.request('POST', path, query=query, data=data)
        return self._unwrap(parsed)

    def patch(self, path, data=None):
        dummy, parsed = self.request('PATCH', path, data=data)
        return self._unwrap(parsed)

    def delete(self, path, data=None):
        dummy, parsed = self.request('DELETE', path, data=data)
        return self._unwrap(parsed)
