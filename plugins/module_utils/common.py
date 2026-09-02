# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Shared plumbing for kenyawest.remnawave modules.

The interesting part is :func:`build_patch`: it compares the desired state
(module options) with the current state (API response) field by field,
using per-field normalization, and produces the minimal PATCH payload.
This is what makes the modules idempotent.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import re
from datetime import datetime

from ansible.module_utils.basic import env_fallback
from ansible.module_utils.common.text.formatters import human_to_bytes


UUID_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


STATE_CHOICES = ['present', 'absent', 'enabled', 'disabled']


def desired_enabled(state):
    """Return True/False when a state pins enabled-ness, else None.

    V(present) deliberately does not pin it: it means "this must exist",
    leaving an already disabled resource disabled.
    """
    if state == 'enabled':
        return True
    if state == 'disabled':
        return False
    return None


def remnawave_argument_spec():
    """Connection options common to every module in this collection."""
    return dict(
        panel_url=dict(
            type='str', required=True,
            fallback=(env_fallback, ['REMNAWAVE_PANEL_URL'])),
        token=dict(
            type='str', required=True, no_log=True,
            fallback=(env_fallback, ['REMNAWAVE_TOKEN'])),
        api_key=dict(
            type='str', no_log=True,
            fallback=(env_fallback, ['REMNAWAVE_API_KEY'])),
        validate_certs=dict(type='bool', default=True),
        timeout=dict(type='int', default=30),
        request_headers=dict(type='dict', default={}),
    )


def is_uuid(value):
    return isinstance(value, str) and bool(UUID_RE.match(value))


def parse_traffic_limit(value):
    """Accept an integer byte count or a human-readable size string.

    Suffixes follow ansible.builtin.human_to_bytes semantics (binary
    multiples: 1G == 1024**3). 0 means unlimited.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('traffic limit must be a number or a size string')
    if isinstance(value, (int, float)):
        return int(value)
    return int(human_to_bytes(value))


def parse_iso_time(value):
    """Parse an ISO 8601 timestamp into an aware/naive datetime, best effort.

    Returns None if the value cannot be parsed; callers then fall back to
    plain string comparison.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def times_equal(a, b):
    da, db = parse_iso_time(a), parse_iso_time(b)
    if da is None or db is None:
        return a == b
    if (da.tzinfo is None) != (db.tzinfo is None):
        # One value carries a timezone and one does not; comparing them
        # directly would raise. Compare the naive representations instead.
        da = da.replace(tzinfo=None)
        db = db.replace(tzinfo=None)
    return da == db


def parse_json_option(value, option_name, module):
    """Accept a dict/list or a JSON-encoded string for an option."""
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError as exc:
            module.fail_json(msg='Option %s is not valid JSON: %s' % (option_name, exc))
    module.fail_json(msg='Option %s must be a dict, a list or a JSON string' % option_name)


class FieldSpec(object):
    """Mapping between one module option and one API field.

    kind:
      scalar - direct comparison after optional to_api conversion
      time   - ISO 8601 timestamps compared as points in time
      set    - lists compared regardless of order and duplicates
      list   - lists compared preserving order
      json   - nested structures compared by deep equality
    """

    def __init__(self, option, api, kind='scalar', to_api=None, from_api=None):
        self.option = option
        self.api = api
        self.kind = kind
        self.to_api = to_api or (lambda v: v)
        self.from_api = from_api or (lambda v: v)

    def equal(self, desired_api_value, current_api_value):
        current = self.from_api(current_api_value)
        if self.kind == 'time':
            return times_equal(desired_api_value, current)
        if self.kind == 'set':
            if desired_api_value is None or current is None:
                return desired_api_value == current
            return sorted(set(desired_api_value)) == sorted(set(current))
        if self.kind in ('list', 'json'):
            return desired_api_value == current
        return desired_api_value == current


def build_patch(params, current, fields):
    """Compute the minimal update payload.

    params  - module.params (an option set to None means "leave untouched")
    current - the resource as returned by the API (or None when creating)
    fields  - list of FieldSpec

    Returns (patch, before, after): ``patch`` maps API field names to the
    desired values that differ from the current state; ``before``/``after``
    hold the same fields in their current/desired form for diff output.
    """
    patch = {}
    before = {}
    after = {}
    for field in fields:
        desired = params.get(field.option)
        if desired is None:
            continue
        desired_api = field.to_api(desired)
        current_api = (current or {}).get(field.api)
        if current is not None and field.equal(desired_api, current_api):
            continue
        patch[field.api] = desired_api
        before[field.api] = current_api if current is not None else None
        after[field.api] = desired_api
    return patch, before, after


def resolve_for_check_mode(module, resolver, fallback):
    """Run a name-to-UUID resolver, tolerating missing references in check mode.

    In check mode, entities referenced by name may not exist yet because the
    tasks that would create them were themselves skipped. Falling back to the
    human-readable names keeps a fresh-panel dry run working; the predicted
    diff then shows names instead of UUIDs.
    """
    from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
        RemnawaveApiError,
    )
    try:
        return resolver()
    except RemnawaveApiError:
        if module.check_mode:
            return fallback
        raise


def exit_with_change(module, before, after, **kwargs):
    result = dict(changed=True, **kwargs)
    if module._diff:
        result['diff'] = dict(before=before, after=after)
    module.exit_json(**result)
