"""A minimal in-memory mock of the Remnawave panel API.

Implements just enough of the v3.4 API surface for the integration
playbook of this collection: bearer-token auth, the optional Caddy
X-Api-Key check, the {"response": ...} envelope, and CRUD for config
profiles, squads, nodes, hosts, users and subscription settings.

Usage: mock_panel.py [port]
Environment: MOCK_TOKEN (default "test-token"),
             MOCK_API_KEY (unset = X-Api-Key not enforced)
"""

import json
import os
import re
import sys
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = os.environ.get('MOCK_TOKEN', 'test-token')
API_KEY = os.environ.get('MOCK_API_KEY')

DB = {
    'config_profiles': {},
    'internal_squads': {},
    'external_squads': {},
    'nodes': {},
    'hosts': {},
    'users': {},
    'subscription_settings': {
        'uuid': str(uuidlib.uuid4()),
        'serveJsonAtBaseSubscription': True,
        'isShowCustomRemarks': True,
        'customRemarks': {},
        'customResponseHeaders': {},
        'randomizeHosts': False,
        'responseRules': {},
        'hwidSettings': None,
    },
    'next_user_id': 1,
}


def new_uuid():
    return str(uuidlib.uuid4())


def profile_inbounds(profile):
    return profile.get('inbounds', [])


def make_profile(name, config):
    inbounds = []
    for inbound in (config or {}).get('inbounds', []):
        inbounds.append({
            'uuid': new_uuid(),
            'tag': inbound.get('tag'),
            'type': inbound.get('protocol'),
            'network': None, 'security': None,
            'port': inbound.get('port'), 'rawInbound': inbound,
        })
    return {
        'uuid': new_uuid(), 'name': name, 'config': config,
        'inbounds': inbounds, 'tags': [], 'viewPosition': 0,
        'nodes': [],
    }


def user_view(user):
    squads = []
    for squad_uuid in user['internalSquadUuids']:
        squad = DB['internal_squads'].get(squad_uuid)
        squads.append({'uuid': squad_uuid,
                       'name': squad['name'] if squad else None})
    view = dict(user)
    del view['internalSquadUuids']
    view['activeInternalSquads'] = squads
    return view


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (self.command, self.path))

    def reply(self, status, payload=None, envelope=True):
        body = b''
        if payload is not None:
            if envelope:
                payload = {'response': payload}
            body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def not_found(self):
        self.reply(404, {'timestamp': 'now', 'path': self.path,
                         'message': 'Resource not found',
                         'errorCode': 'NOT_FOUND'}, envelope=False)

    def read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length))

    def authorized(self):
        if API_KEY and self.headers.get('X-Api-Key') != API_KEY:
            self.reply(404, None)
            return False
        if self.headers.get('Authorization') != 'Bearer %s' % TOKEN:
            self.reply(401, {'message': 'Unauthorized'}, envelope=False)
            return False
        return True

    # --- routing -------------------------------------------------------

    def handle_any(self):
        if not self.authorized():
            return
        path = self.path.split('?')[0]
        method = self.command
        for pattern, handler in ROUTES:
            match = re.fullmatch(pattern, '%s %s' % (method, path))
            if match:
                handler(self, *match.groups())
                return
        self.not_found()

    do_GET = do_POST = do_PATCH = do_DELETE = handle_any


# --- resource handlers -------------------------------------------------

def collection_handlers(store_key, list_key, make):
    """Generic list/create/update/delete for name-identified collections."""

    def list_items(handler):
        items = list(DB[store_key].values())
        handler.reply(200, {'total': len(items), list_key: items})

    def create(handler):
        body = handler.read_body()
        item = make(body)
        DB[store_key][item['uuid']] = item
        handler.reply(201, item)

    def update(handler):
        body = handler.read_body()
        item = DB[store_key].get(body.get('uuid'))
        if not item:
            handler.not_found()
            return
        for key, value in body.items():
            if key != 'uuid':
                item[key] = value
        handler.reply(200, item)

    def delete(handler, item_uuid):
        if DB[store_key].pop(item_uuid, None) is None:
            handler.not_found()
            return
        handler.reply(200, {'isDeleted': True})

    return list_items, create, update, delete


cp_list, _cp_create_generic, cp_update, cp_delete = collection_handlers(
    'config_profiles', 'configProfiles', lambda b: make_profile(b['name'], b.get('config')))


def cp_create(handler):
    body = handler.read_body()
    item = make_profile(body['name'], body.get('config'))
    DB['config_profiles'][item['uuid']] = item
    handler.reply(201, item)


def cp_update_config(handler):
    body = handler.read_body()
    item = DB['config_profiles'].get(body.get('uuid'))
    if not item:
        handler.not_found()
        return
    if 'config' in body:
        rebuilt = make_profile(item['name'], body['config'])
        item['config'] = body['config']
        item['inbounds'] = rebuilt['inbounds']
    if 'name' in body:
        item['name'] = body['name']
    handler.reply(200, item)


def make_internal_squad(body):
    return {
        'uuid': new_uuid(), 'name': body['name'], 'tags': [],
        'viewPosition': 0,
        'info': {'membersCount': 0, 'inboundsCount': len(body.get('inbounds', []))},
        'inbounds': [{'uuid': u} for u in body.get('inbounds', [])],
    }


isq_list, isq_create, _isq_update_generic, isq_delete = collection_handlers(
    'internal_squads', 'internalSquads', make_internal_squad)


def isq_update(handler):
    body = handler.read_body()
    item = DB['internal_squads'].get(body.get('uuid'))
    if not item:
        handler.not_found()
        return
    if 'inbounds' in body:
        item['inbounds'] = [{'uuid': u} for u in body['inbounds']]
        item['info']['inboundsCount'] = len(body['inbounds'])
    if 'name' in body:
        item['name'] = body['name']
    handler.reply(200, item)


esq_list, esq_create, esq_update, esq_delete = collection_handlers(
    'external_squads', 'externalSquads',
    lambda b: {'uuid': new_uuid(), 'name': b['name'], 'tags': [],
               'viewPosition': 0, 'info': {'membersCount': 0}})


def make_node(body):
    profile = body.get('configProfile', {})
    node = {
        'uuid': new_uuid(), 'id': 1, 'name': body['name'],
        'address': body.get('address'), 'port': body.get('port', 2222),
        'isDisabled': False, 'isConnected': False, 'isConnecting': False,
        'isTrafficTrackingActive': body.get('isTrafficTrackingActive', False),
        'trafficLimitBytes': body.get('trafficLimitBytes', 0),
        'trafficUsedBytes': 0,
        'notifyPercent': body.get('notifyPercent', 0),
        'trafficResetDay': body.get('trafficResetDay', 1),
        'countryCode': body.get('countryCode', 'XX'),
        'consumptionMultiplier': body.get('consumptionMultiplier', 1),
        'tags': body.get('tags', []), 'note': body.get('note'),
        'configProfile': {
            'activeConfigProfileUuid': profile.get('activeConfigProfileUuid'),
            'activeInbounds': [
                {'uuid': u} for u in profile.get('activeInbounds', [])],
        },
    }
    return node


def node_list(handler):
    handler.reply(200, list(DB['nodes'].values()))


def node_create(handler):
    body = handler.read_body()
    node = make_node(body)
    DB['nodes'][node['uuid']] = node
    handler.reply(201, node)


def node_update(handler):
    body = handler.read_body()
    node = DB['nodes'].get(body.get('uuid'))
    if not node:
        handler.not_found()
        return
    for key, value in body.items():
        if key == 'configProfile':
            node['configProfile'] = {
                'activeConfigProfileUuid': value.get('activeConfigProfileUuid'),
                'activeInbounds': [
                    {'uuid': u} for u in value.get('activeInbounds', [])],
            }
        elif key != 'uuid':
            node[key] = value
    handler.reply(200, node)


def node_delete(handler, node_uuid):
    if DB['nodes'].pop(node_uuid, None) is None:
        handler.not_found()
        return
    handler.reply(200, {'isDeleted': True})


def node_action(handler, node_uuid, action):
    node = DB['nodes'].get(node_uuid)
    if not node:
        handler.not_found()
        return
    if action in ('enable', 'disable'):
        node['isDisabled'] = (action == 'disable')
    handler.reply(200, node)


def make_host(body):
    host = {
        'uuid': new_uuid(), 'viewPosition': 0,
        'remark': body['remark'], 'address': body.get('address'),
        'port': body.get('port'), 'path': body.get('path'),
        'sni': body.get('sni'), 'host': body.get('host'),
        'alpn': body.get('alpn'), 'fingerprint': body.get('fingerprint'),
        'isDisabled': body.get('isDisabled', False),
        'securityLayer': body.get('securityLayer', 'DEFAULT'),
        'isHidden': body.get('isHidden', False),
        'tags': body.get('tags', []),
        'serverDescription': body.get('serverDescription'),
        'inbound': body.get('inbound', {}),
        'nodes': body.get('nodes', []),
    }
    return host


hosts_list_raw, _h_create, host_update, host_delete = collection_handlers(
    'hosts', 'hosts', make_host)


def host_list(handler):
    handler.reply(200, list(DB['hosts'].values()))


def host_create(handler):
    body = handler.read_body()
    host = make_host(body)
    DB['hosts'][host['uuid']] = host
    handler.reply(201, host)


def hosts_bulk(handler, action):
    body = handler.read_body()
    for host_uuid in body.get('uuids', []):
        if action == 'delete':
            DB['hosts'].pop(host_uuid, None)
        elif host_uuid in DB['hosts']:
            DB['hosts'][host_uuid]['isDisabled'] = (action == 'disable')
    handler.reply(204, None)


def user_action(handler, user_id, action):
    user = DB['users'].get(int(user_id))
    if not user:
        handler.not_found()
        return
    user['status'] = 'DISABLED' if action == 'disable' else 'ACTIVE'
    handler.reply(200, user_view(user))


def make_user(body):
    user = {
        'id': DB['next_user_id'], 'shortUuid': new_uuid()[:8],
        'username': body['username'],
        'status': body.get('status', 'ACTIVE'),
        'trafficLimitBytes': body.get('trafficLimitBytes', 0),
        'trafficLimitStrategy': body.get('trafficLimitStrategy', 'NO_RESET'),
        'expireAt': body.get('expireAt'),
        'description': body.get('description'), 'tag': body.get('tag'),
        'email': body.get('email'), 'telegramId': body.get('telegramId'),
        'hwidDeviceLimit': body.get('hwidDeviceLimit'),
        'externalSquadUuid': body.get('externalSquadUuid'),
        'internalSquadUuids': body.get('activeInternalSquads', []),
        'trojanPassword': 'secret', 'vlessUuid': new_uuid(),
        'ssPassword': 'secret', 'subscriptionUrl': 'https://sub.example/abc',
        'userTraffic': {'usedTrafficBytes': 0, 'lifetimeUsedTrafficBytes': 0},
    }
    DB['next_user_id'] += 1
    return user


def user_create(handler):
    body = handler.read_body()
    user = make_user(body)
    DB['users'][user['id']] = user
    handler.reply(201, user_view(user))


def user_update(handler):
    body = handler.read_body()
    user = DB['users'].get(body.get('id'))
    if not user:
        handler.not_found()
        return
    for key, value in body.items():
        if key == 'activeInternalSquads':
            user['internalSquadUuids'] = value
        elif key != 'id':
            user[key] = value
    handler.reply(200, user_view(user))


def user_list(handler):
    users = [user_view(u) for u in DB['users'].values()]
    handler.reply(200, {'total': len(users), 'users': users})


def user_by_username(handler, username):
    for user in DB['users'].values():
        if user['username'] == username:
            handler.reply(200, user_view(user))
            return
    handler.not_found()


def user_delete(handler, user_id):
    if DB['users'].pop(int(user_id), None) is None:
        handler.not_found()
        return
    handler.reply(200, {'isDeleted': True})


def subscription_settings_get(handler):
    handler.reply(200, DB['subscription_settings'])


def subscription_settings_update(handler):
    body = handler.read_body()
    for key, value in body.items():
        if key != 'uuid':
            DB['subscription_settings'][key] = value
    handler.reply(200, DB['subscription_settings'])


def health(handler):
    handler.reply(200, {'pm2Stats': [], 'isHealthy': True})


UUID = r'[0-9a-f-]{36}'
ROUTES = [
    (r'GET /api/config-profiles', cp_list),
    (r'POST /api/config-profiles', cp_create),
    (r'PATCH /api/config-profiles', cp_update_config),
    (r'DELETE /api/config-profiles/(%s)' % UUID, cp_delete),
    (r'GET /api/internal-squads', isq_list),
    (r'POST /api/internal-squads', isq_create),
    (r'PATCH /api/internal-squads', isq_update),
    (r'DELETE /api/internal-squads/(%s)' % UUID, isq_delete),
    (r'GET /api/external-squads', esq_list),
    (r'POST /api/external-squads', esq_create),
    (r'PATCH /api/external-squads', esq_update),
    (r'DELETE /api/external-squads/(%s)' % UUID, esq_delete),
    (r'GET /api/nodes', node_list),
    (r'POST /api/nodes', node_create),
    (r'PATCH /api/nodes', node_update),
    (r'DELETE /api/nodes/(%s)' % UUID, node_delete),
    (r'POST /api/nodes/(%s)/actions/(enable|disable)' % UUID, node_action),
    (r'GET /api/hosts', host_list),
    (r'POST /api/hosts', host_create),
    (r'PATCH /api/hosts', host_update),
    (r'DELETE /api/hosts/(%s)' % UUID, host_delete),
    (r'POST /api/hosts/bulk/(enable|disable|delete)', hosts_bulk),
    (r'POST /api/users/(\d+)/actions/(enable|disable)', user_action),
    (r'POST /api/users', user_create),
    (r'PATCH /api/users', user_update),
    (r'GET /api/users', user_list),
    (r'GET /api/users/by-username/([^/]+)', user_by_username),
    (r'DELETE /api/users/(\d+)', user_delete),
    (r'GET /api/subscription-settings', subscription_settings_get),
    (r'PATCH /api/subscription-settings', subscription_settings_update),
    (r'GET /api/system/health', health),
]


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8443
    server = HTTPServer(('127.0.0.1', port), Handler)
    sys.stderr.write('mock panel listening on 127.0.0.1:%d\n' % port)
    server.serve_forever()


if __name__ == '__main__':
    main()
