# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Planning and applying the desired state of hosts.

Shared by the host module, which manages one host per task, and the hosts
module, which manages many in a single task. Planning only reads the panel
and applying only writes to it, so a batch can plan every entry - and
refuse the whole batch over a bad one - before it changes anything.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import (
    STATE_CHOICES, FieldSpec, build_patch, desired_enabled,
    resolve_for_check_mode, validate_tags,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.resources import (
    find_host, resolve_inbound_uuids, resolve_internal_squad_uuids,
    resolve_node_uuids,
)


# Only one of them must be set, depending on which identifies the host.
HOST_REQUIRED_IF = [('identify_by', 'remark', ['remark']),
                    ('identify_by', 'address', ['address'])]


def host_options():
    """The options describing one host, without the connection options."""
    return dict(
        identify_by=dict(type='str', choices=['remark', 'address'],
                         default='remark'),
        remark=dict(type='str'),
        state=dict(type='str', choices=STATE_CHOICES, default='present'),
        nodes=dict(type='list', elements='str'),
        config_profile=dict(type='str'),
        inbound=dict(type='str'),
        address=dict(type='str'),
        port=dict(type='int'),
        path=dict(type='str'),
        sni=dict(type='str'),
        host_header=dict(type='str'),
        alpn=dict(type='str',
                  choices=['h3', 'h2', 'http/1.1', 'h2,http/1.1',
                           'h3,h2,http/1.1', 'h3,h2']),
        fingerprint=dict(type='str'),
        security_layer=dict(type='str', choices=['default', 'tls', 'none']),
        hidden=dict(type='bool'),
        tags=dict(type='list', elements='str'),
        server_description=dict(type='str'),
        vless_route_id=dict(type='raw'),
        override_sni_from_address=dict(type='bool'),
        keep_sni_blank=dict(type='bool'),
        exclude_from_subscription_types=dict(
            type='list', elements='str',
            choices=['XRAY_JSON', 'XRAY_BASE64', 'MIHOMO', 'STASH', 'CLASH',
                     'SINGBOX']),
        internal_squads=dict(type='dict', options=dict(
            mode=dict(type='str', choices=['exclude', 'allow_only'],
                      required=True),
            squads=dict(type='list', elements='str', required=True),
        )),
    )


def to_route_id(value):
    """Normalize the vless_route_id option into an int or None.

    Empty string clears the field, matching how the other nullable host
    options are cleared.
    """
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('vless_route_id must be an integer between 0 and '
                         '65535, or an empty string to clear it')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError('vless_route_id must be an integer between 0 and '
                         '65535, or an empty string to clear it, got %r'
                         % (value,))
    if not 0 <= number <= 65535:
        raise ValueError('vless_route_id must be between 0 and 65535, got %d'
                         % number)
    return number


def build_fields(module, client, params):
    fields = [
        FieldSpec('address', 'address'),
        FieldSpec('port', 'port'),
        FieldSpec('path', 'path', to_api=lambda v: v or None),
        FieldSpec('sni', 'sni', to_api=lambda v: v or None),
        FieldSpec('host_header', 'host', to_api=lambda v: v or None),
        FieldSpec('alpn', 'alpn'),
        FieldSpec('fingerprint', 'fingerprint', to_api=lambda v: v or None),
        FieldSpec('security_layer', 'securityLayer', to_api=lambda v: v.upper()),
        FieldSpec('hidden', 'isHidden'),
        FieldSpec('tags', 'tags', kind='set', to_api=validate_tags),
        FieldSpec('server_description', 'serverDescription',
                  to_api=lambda v: v or None),
        FieldSpec('vless_route_id', 'vlessRouteId', to_api=to_route_id),
        FieldSpec('override_sni_from_address', 'overrideSniFromAddress'),
        FieldSpec('keep_sni_blank', 'keepSniBlank'),
        FieldSpec('exclude_from_subscription_types',
                  'excludeFromSubscriptionTypes', kind='set'),
    ]
    resolved = dict(params)

    if params['identify_by'] != 'remark' and params['remark'] is not None:
        # Not the identifier here, so it is an ordinary field and may be
        # used to rename the host.
        fields.append(FieldSpec('remark', 'remark'))

    wanted_enabled = desired_enabled(params['state'])
    if wanted_enabled is not None:
        # state enabled/disabled is just the isDisabled field for a host.
        resolved['is_disabled'] = not wanted_enabled
        fields.append(FieldSpec('is_disabled', 'isDisabled'))

    if params['nodes'] is not None:
        resolved['nodes'] = resolve_for_check_mode(
            module,
            lambda: resolve_node_uuids(client, params['nodes']),
            list(params['nodes']))
        fields.append(FieldSpec('nodes', 'nodes', kind='set'))

    if params['internal_squads'] is not None:
        squads = params['internal_squads']
        resolved['internal_squads'] = {
            'mode': squads['mode'].upper(),
            'squads': sorted(resolve_for_check_mode(
                module,
                lambda: resolve_internal_squad_uuids(client, squads['squads']),
                list(squads['squads']))),
        }
        fields.append(FieldSpec(
            'internal_squads', 'internalSquads', kind='json',
            from_api=lambda v: {
                'mode': (v or {}).get('mode'),
                'squads': sorted((v or {}).get('squads') or []),
            }))

    if params['config_profile'] is not None or params['inbound'] is not None:
        # The inbound alone suffices: its tag is unique across profiles, so
        # it names its profile too.
        if params['inbound'] is None:
            raise ValueError('config_profile requires inbound')
        profile_uuid, inbound_uuids = resolve_for_check_mode(
            module,
            lambda: resolve_inbound_uuids(
                client, params['config_profile'], [params['inbound']]),
            (params['config_profile'], [params['inbound']]))
        resolved['config_profile'] = {
            'configProfileUuid': profile_uuid,
            'configProfileInboundUuid': inbound_uuids[0],
        }
        fields.append(FieldSpec(
            'config_profile', 'inbound', kind='json',
            from_api=lambda v: {
                'configProfileUuid': (v or {}).get('configProfileUuid'),
                'configProfileInboundUuid': (v or {}).get('configProfileInboundUuid'),
            }))
    return fields, resolved


def plan_host(module, client, params):
    """Work out what one host needs, without changing anything.

    ``params`` holds the options of one host. Returns a dict with the
    ``action`` to take (``create``, ``update``, ``delete`` or ``none``),
    the host as found on the panel (``current``), the request ``payload``
    and the ``before``/``after`` diff.
    """
    identify_by = params['identify_by']
    identifier = params[identify_by]
    if identifier is None:
        raise ValueError(
            'Option %s is required, because identify_by=%s makes it the '
            'identifier of the host' % (identify_by, identify_by))
    current = find_host(client, identifier, key=identify_by)
    plan = dict(identify_by=identify_by, identifier=identifier,
                current=current, action='none', payload=None,
                before={}, after={})

    if params['state'] == 'absent':
        if current is not None:
            plan.update(action='delete', before={identify_by: identifier})
        return plan

    fields, resolved = build_fields(module, client, params)
    patch, before, after = build_patch(resolved, current, fields)

    if current is None:
        missing = [opt for opt in ('inbound', 'address', 'port')
                   if params[opt] is None]
        if missing:
            raise ValueError('Creating host %r requires: %s'
                             % (identifier, ', '.join(missing)))
        payload = dict(patch)
        # The API always wants a remark; when hosts are addressed by domain
        # and no remark is given, the domain is the obvious display name.
        payload['remark'] = params['remark'] or params['address']
        plan.update(action='create', payload=payload,
                    after=dict(after, remark=payload['remark']))
        return plan

    if patch:
        payload = dict(patch)
        payload['uuid'] = current['uuid']
        plan.update(action='update', payload=payload,
                    before=before, after=after)
    return plan


def apply_host_plan(module, client, plan):
    """Carry out a plan (only pretending in check mode).

    Returns the module result for that host: ``changed``, the ``host`` as
    it is now (or would be), and a ``diff`` in diff mode.
    """
    action = plan['action']
    current = plan['current']
    result = dict(changed=action != 'none')
    if action == 'none':
        if current is not None:
            result['host'] = current
        return result

    if action == 'delete':
        if not module.check_mode:
            client.delete('/api/hosts/%s' % current['uuid'])
    elif action == 'create':
        result['host'] = (plan['payload'] if module.check_mode
                          else client.post('/api/hosts', plan['payload']))
    else:
        result['host'] = (current if module.check_mode
                          else client.patch('/api/hosts', plan['payload']))
    if module._diff:
        result['diff'] = dict(before=plan['before'], after=plan['after'])
    return result


def entry_label(index, entry):
    identify_by = entry['identify_by']
    return 'hosts[%d] (%s %r)' % (index, identify_by, entry.get(identify_by))


def plan_hosts(module, client, entries):
    """Plan every entry of a batch; raises over the first bad one.

    Entries are planned against the panel as it is before the batch, so
    one entry cannot build on another's change, and each host may be
    declared only once. Raised errors name the offending entry.
    """
    plans = []
    claimed = {}
    for index, entry in enumerate(entries):
        label = entry_label(index, entry)
        try:
            plan = plan_host(module, client, entry)
        except RemnawaveApiError as exc:
            raise RemnawaveApiError('%s: %s' % (label, exc), status=exc.status,
                                    error_code=exc.error_code, body=exc.body)
        except ValueError as exc:
            raise ValueError('%s: %s' % (label, exc))

        current = plan['current']
        if current is not None:
            key = ('uuid', current['uuid'])
        else:
            key = (plan['identify_by'], plan['identifier'])
        if key in claimed:
            raise ValueError('%s and %s address the same host; declare each '
                             'host once' % (claimed[key], label))
        claimed[key] = label
        plan['label'] = label
        plans.append(plan)
    return plans
