# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Lookup and name-to-UUID resolution helpers.

Playbooks reference Remnawave entities by stable human identifiers
(config profile names, inbound tags, squad names, node names). These
helpers translate them into the UUIDs the API expects, so UUIDs never
have to appear in playbooks.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import (
    RemnawaveApiError,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.common import is_uuid


def list_config_profiles(client):
    data = client.get('/api/config-profiles')
    return (data or {}).get('configProfiles', [])


def find_config_profile(client, name_or_uuid, required=False):
    profiles = list_config_profiles(client)
    key = 'uuid' if is_uuid(name_or_uuid) else 'name'
    matches = [p for p in profiles if p.get(key) == name_or_uuid]
    if not matches:
        if required:
            raise RemnawaveApiError('Config profile %r not found' % name_or_uuid)
        return None
    return matches[0]


def resolve_inbound_uuids(client, profile, inbounds):
    """Resolve a config profile plus a list of inbound tags/UUIDs.

    Returns (profile_uuid, [inbound_uuid, ...]).
    """
    profile_obj = find_config_profile(client, profile, required=True)
    by_tag = dict((i.get('tag'), i.get('uuid')) for i in profile_obj.get('inbounds', []))
    uuids = []
    for item in inbounds or []:
        if is_uuid(item):
            uuids.append(item)
        elif item in by_tag:
            uuids.append(by_tag[item])
        else:
            raise RemnawaveApiError(
                'Inbound %r not found in config profile %r (available tags: %s)'
                % (item, profile_obj.get('name'), ', '.join(sorted(k for k in by_tag if k))))
    return profile_obj['uuid'], uuids


def list_internal_squads(client):
    data = client.get('/api/internal-squads')
    return (data or {}).get('internalSquads', [])


def find_internal_squad(client, name_or_uuid, required=False):
    squads = list_internal_squads(client)
    key = 'uuid' if is_uuid(name_or_uuid) else 'name'
    matches = [s for s in squads if s.get(key) == name_or_uuid]
    if not matches:
        if required:
            raise RemnawaveApiError('Internal squad %r not found' % name_or_uuid)
        return None
    return matches[0]


def resolve_internal_squad_uuids(client, names_or_uuids):
    squads = list_internal_squads(client)
    by_name = dict((s.get('name'), s.get('uuid')) for s in squads)
    uuids = []
    for item in names_or_uuids or []:
        if is_uuid(item):
            uuids.append(item)
        elif item in by_name:
            uuids.append(by_name[item])
        else:
            raise RemnawaveApiError(
                'Internal squad %r not found (available: %s)'
                % (item, ', '.join(sorted(k for k in by_name if k))))
    return uuids


def list_external_squads(client):
    data = client.get('/api/external-squads')
    return (data or {}).get('externalSquads', [])


def find_external_squad(client, name_or_uuid, required=False):
    squads = list_external_squads(client)
    key = 'uuid' if is_uuid(name_or_uuid) else 'name'
    matches = [s for s in squads if s.get(key) == name_or_uuid]
    if not matches:
        if required:
            raise RemnawaveApiError('External squad %r not found' % name_or_uuid)
        return None
    return matches[0]


def list_nodes(client):
    return client.get('/api/nodes') or []


def find_node(client, name_or_uuid, required=False):
    nodes = list_nodes(client)
    key = 'uuid' if is_uuid(name_or_uuid) else 'name'
    matches = [n for n in nodes if n.get(key) == name_or_uuid]
    if not matches:
        if required:
            raise RemnawaveApiError('Node %r not found' % name_or_uuid)
        return None
    return matches[0]


def list_hosts(client):
    return client.get('/api/hosts') or []


def find_hosts_by(client, value, key='remark'):
    """All hosts whose ``key`` (or uuid) equals ``value``.

    ``key`` is the identifier the caller addresses hosts by: ``remark`` or
    ``address``. A UUID always wins over either.
    """
    hosts = list_hosts(client)
    lookup = 'uuid' if is_uuid(value) else key
    return [h for h in hosts if h.get(lookup) == value]


def find_host(client, value, key='remark', required=False):
    """The single host identified by ``value``; fails on ambiguity.

    Remarks are unique in practice; addresses are not, since one domain can
    serve several inbounds or ports. Rather than picking one arbitrarily,
    an ambiguous identifier is an error; host_info lists the candidates.
    """
    matches = find_hosts_by(client, value, key=key)
    if len(matches) > 1:
        raise RemnawaveApiError(
            'Multiple hosts share the %s %r (remarks: %s); identify the host '
            'you mean by remark, or give each of them its own address'
            % (key, value, ', '.join(sorted(repr(h.get('remark')) for h in matches))))
    if not matches:
        if required:
            raise RemnawaveApiError('Host with %s %r not found' % (key, value))
        return None
    return matches[0]


def resolve_node_uuids(client, names_or_uuids):
    nodes = list_nodes(client)
    by_name = dict((n.get('name'), n.get('uuid')) for n in nodes)
    uuids = []
    for item in names_or_uuids or []:
        if is_uuid(item):
            uuids.append(item)
        elif item in by_name:
            uuids.append(by_name[item])
        else:
            raise RemnawaveApiError(
                'Node %r not found (available: %s)'
                % (item, ', '.join(sorted(k for k in by_name if k))))
    return uuids


def hosts_linked_to_node(client, node_uuid):
    """Hosts explicitly bound to one node.

    A host with an empty ``nodes`` list is served from every node rather
    than bound to this one, so it is deliberately not considered linked:
    decommissioning a single node must not disable panel-wide hosts.
    """
    return [h for h in list_hosts(client)
            if node_uuid in (h.get('nodes') or [])]


def bulk_host_action(client, action, uuids):
    """Apply enable/disable/delete to many hosts in one request."""
    if not uuids:
        return
    client.post('/api/hosts/bulk/%s' % action, {'uuids': list(uuids)})


def list_snippets(client):
    data = client.get('/api/snippets')
    return (data or {}).get('snippets', [])


def find_snippet(client, name, required=False):
    """The snippet with this name, or None.

    Snippets are keyed by name throughout the API - there is no UUID - so
    every operation, deletion included, addresses them this way.
    """
    matches = [s for s in list_snippets(client) if s.get('name') == name]
    if not matches:
        if required:
            raise RemnawaveApiError('Snippet %r not found' % name)
        return None
    return matches[0]


def _written_snippet(data, name, content):
    """The single snippet out of a create or update response.

    Writes answer with the same envelope as the listing - a total and a
    list of snippets - so unwrap it back to the one that was addressed.
    """
    for item in (data or {}).get('snippets', []):
        if item.get('name') == name:
            return item
    return {'name': name, 'snippet': content}


def create_snippet(client, name, content):
    data = client.post('/api/snippets', {'name': name, 'snippet': content})
    return _written_snippet(data, name, content)


def update_snippet(client, name, content):
    data = client.patch('/api/snippets', {'name': name, 'snippet': content})
    return _written_snippet(data, name, content)


def sync_snippet(client, name):
    """Push a snippet's current content into the config profiles using it."""
    client.post('/api/snippets/actions/sync', {'name': name})


def get_user_by_username(client, username):
    return client.get('/api/users/by-username/%s' % username, allow_404=True)


def user_action(client, user_id, action):
    """Apply an enable/disable action to one user."""
    return client.post('/api/users/%s/actions/%s' % (user_id, action))
