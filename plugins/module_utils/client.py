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

    def request(self, method, path, query=None, data=None, ok_statuses=None):
        """Perform a request and return ``(status, parsed_json_or_None)``.

        ``ok_statuses`` is an optional iterable of extra HTTP statuses that
        must not raise (e.g. 404 when probing for existence).
        """
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

        response, info = fetch_url(
            self.module, url, data=body, headers=self.headers,
            method=method, timeout=self.timeout,
        )

        status = info['status']
        raw = b''
        if response is not None:
            raw = response.read()
        elif info.get('body'):
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

    def get(self, path, query=None, allow_404=False):
        ok = (404,) if allow_404 else ()
        status, parsed = self.request('GET', path, query=query, ok_statuses=ok)
        if status == 404:
            return None
        return self._unwrap(parsed)

    def post(self, path, data=None, query=None):
        dummy, parsed = self.request('POST', path, query=query, data=data)
        return self._unwrap(parsed)

    def patch(self, path, data=None):
        dummy, parsed = self.request('PATCH', path, data=data)
        return self._unwrap(parsed)

    def delete(self, path, data=None):
        dummy, parsed = self.request('DELETE', path, data=data)
        return self._unwrap(parsed)
