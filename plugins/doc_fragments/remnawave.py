# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r'''
options:
  panel_url:
    description:
      - Base URL of the Remnawave panel, for example C(https://panel.example.com).
      - If the panel is protected by Caddy with a custom path, this is still the
        base URL; authentication for the protection layer is passed via O(api_key).
      - Falls back to the E(REMNAWAVE_PANEL_URL) environment variable.
    type: str
    required: true
  token:
    description:
      - Remnawave API token (created in the panel under API Tokens) or a JWT
        obtained via login. Sent as a bearer token.
      - Falls back to the E(REMNAWAVE_TOKEN) environment variable.
    type: str
    required: true
  api_key:
    description:
      - Value for the C(X-Api-Key) header used by the Caddy
        "security via custom path" setup described at
        U(https://docs.rw/security/caddy-with-custom-path).
      - Leave unset when the panel is not behind that protection layer.
      - Falls back to the E(REMNAWAVE_API_KEY) environment variable.
    type: str
  validate_certs:
    description:
      - Whether to validate TLS certificates of the panel.
      - Only disable this against trusted panels with self-signed certificates.
    type: bool
    default: true
  timeout:
    description:
      - Timeout for API requests, in seconds.
    type: int
    default: 30
  request_headers:
    description:
      - Additional HTTP headers to send with every request.
      - Useful for example when talking to the panel directly without a reverse
        proxy, where Remnawave expects C(X-Forwarded-For) and
        C(X-Forwarded-Proto) headers.
    type: dict
    default: {}
requirements:
  - Python 3.9 or newer on the target (modules only use the standard library)
notes:
  - All modules of this collection talk to the Remnawave HTTP API; they are
    typically run against C(localhost) or with C(delegate_to localhost).
  - All modules support check mode and diff mode unless stated otherwise.
  - Connection options can be set once for all modules of this collection via
    C(module_defaults) with the group C(group/kenyawest.remnawave.remnawave).
'''
