# kenyawest.remnawave

Ansible collection for declarative management of a [Remnawave](https://remna.st/)
panel over its HTTP API: users, nodes, hosts, config profiles, squads and
subscription settings.

## Design

This collection deliberately does not mirror the Remnawave API. The API has
more than 160 endpoints and is version-coupled to the panel; wrapping each
endpoint in a module would replicate that churn into your playbooks. Instead,
the collection models a small number of *resources* and their desired state,
the way Ansible modules are supposed to work:

- You describe what should exist; modules read the current state, compare the
  fields you set, and apply the minimal change. Running the same play twice
  yields `changed=0`.
- Entities are addressed by stable human identifiers (username, node name,
  host remark, profile name). Cross-references such as squads, config
  profiles and inbounds are given by name or tag and resolved to UUIDs
  internally. UUIDs never need to appear in playbooks.
- One resource module may use several API endpoints internally (for example,
  enabling a node is an action endpoint, but you express it as `enabled:
  true`). Conversely, most endpoints are intentionally not exposed at all.
- Imperative API actions that have no persistent desired state (reset
  traffic, restart node, revoke subscription) are not pretended to be
  idempotent. They are available through the `api` escape-hatch module and
  are documented as non-idempotent.

The layering, from bottom to top:

    Remnawave HTTP API            (unstable, version-coupled)
      plugins/module_utils/       (client, normalization, name resolution)
        resource modules          (user, node, host, ...)
          remnawave role          (loops over desired-state variables)
            your playbooks        (stable declarative contract)

## Compatibility

Developed and tested against the Remnawave API specification **v3.4.3**.
The collection does not promise compatibility with every Remnawave release;
when the panel API changes incompatibly, a new collection release will state
the supported range in this section and in the changelog.

Requires ansible-core 2.15 or newer and Python 3.9 or newer. Modules use
only the Python standard library.

## Contents

### Modules

| Module | Purpose |
| --- | --- |
| `user`, `user_info` | Panel users: expiration, traffic limits, squad membership, enable/disable |
| `node`, `node_info` | Nodes: address, active config profile and inbounds, enable/disable, traffic accounting, cascade onto linked hosts |
| `host`, `host_info` | Subscription hosts: address, SNI, transport parameters, node binding, visibility |
| `config_profile`, `config_profile_info` | Xray config profiles (the supplied config is authoritative) |
| `internal_squad`, `internal_squad_info` | Internal squads and their inbounds |
| `external_squad`, `external_squad_info` | External squads |
| `subscription_settings` | Panel-wide subscription settings (singleton) |
| `system_info` | Health, statistics, metadata; doubles as a credentials check |
| `api` | Low-level escape hatch for anything not modeled above |

Every state module supports check mode (`--check`) and diff mode (`--diff`)
and only manages the options you set: omitted options are left untouched on
the panel. List-valued options (`internal_squads`, `inbounds`, `tags`,
`nodes`) are authoritative when set.

### The `state` property

`user`, `node` and `host` share one well-known `state` property:

| `state` | Meaning |
| --- | --- |
| `present` (default) | The entity exists and its managed fields match. Its enabled/disabled status is **not** touched, so something disabled in the panel stays disabled. |
| `enabled` | As `present`, and the entity is enabled. Created first if missing. |
| `disabled` | As `present`, and the entity is disabled. Created disabled if missing. |
| `absent` | The entity is deleted. |

The other modules (`config_profile`, `internal_squad`, `external_squad`) have
no enabled/disabled concept and accept `present`/`absent` only.

For users, the panel derives `LIMITED` (over quota) and `EXPIRED` itself.
`state: enabled` treats those as already satisfied rather than forcing them
back to `ACTIVE`, which the panel would undo on its next pass.

### Decommissioning a node with its hosts

Hosts can be bound to specific nodes (`host: nodes: [...]`). The `node`
module can carry that binding along when a node is taken out of service,
through `linked_hosts`:

```yaml
# Disable the node and every host bound to it
- kenyawest.remnawave.node:
    name: nl-ams-1
    state: disabled
    linked_hosts: disable

# Delete the node and every host bound to it
- kenyawest.remnawave.node:
    name: nl-ams-1
    state: absent
    linked_hosts: delete

# Disable the hosts of a node without touching the node itself
- kenyawest.remnawave.node:
    name: nl-ams-1
    state: present
    linked_hosts: disable

# Put a node back into service together with its hosts
- kenyawest.remnawave.node:
    name: nl-ams-1
    state: enabled
    linked_hosts: enable
```

`linked_hosts` accepts `ignore` (the default), `enable`, `disable` and
`delete`. Notes:

- Only hosts **explicitly bound** to the node are affected. A host bound to
  no node is served from every node, so a single node going away never
  disables or deletes it.
- With `state: absent` the hosts are handled first, while the binding can
  still be resolved. If the node is already gone, nothing is cascaded,
  because there is no way left to tell which hosts were linked to it.
- The task reports the affected hosts in `linked_hosts`, and check mode
  predicts them without touching anything.
- If you also declare those hosts in the same play, give them
  `state: present` rather than `enabled`, otherwise the host task will
  immediately re-enable what the cascade just disabled.

### Role

The `remnawave` role applies a whole desired state described by variables
(`remnawave_users`, `remnawave_nodes`, `remnawave_hosts`,
`remnawave_config_profiles`, `remnawave_internal_squads`,
`remnawave_external_squads`, `remnawave_subscription_settings`) in dependency
order. See `roles/remnawave/README.md`.

## Installation

From Ansible Galaxy:

    ansible-galaxy collection install kenyawest.remnawave

From a Git checkout:

    ansible-galaxy collection install git+https://github.com/Kenya-West/remnawave-ansible-collection.git

## Authentication

Every module takes the same connection options:

- `panel_url` - base URL of the panel;
- `token` - an API token created in the panel (sent as a bearer token);
- `api_key` - optional; the value of the `X-Api-Key` header for panels
  protected by the Caddy "security via custom path" setup
  ([docs.rw/security/caddy-with-custom-path](https://docs.rw/security/caddy-with-custom-path));
- `validate_certs`, `timeout`, `request_headers`.

All three credentials fall back to the environment variables
`REMNAWAVE_PANEL_URL`, `REMNAWAVE_TOKEN` and `REMNAWAVE_API_KEY`.

If you call the panel directly on its own port, without a reverse proxy,
Remnawave expects forwarding headers; supply them via `request_headers`:

```yaml
request_headers:
  X-Forwarded-For: 127.0.0.1
  X-Forwarded-Proto: https
```

Instead of repeating connection options on every task, set them once per play
through the collection's action group:

```yaml
module_defaults:
  group/kenyawest.remnawave.remnawave:
    panel_url: https://panel.example.com
    token: "{{ vault_remnawave_token }}"
    api_key: "{{ vault_remnawave_api_key }}"
```

## Quick start

```yaml
- hosts: localhost
  gather_facts: false
  module_defaults:
    group/kenyawest.remnawave.remnawave:
      panel_url: https://panel.example.com
      token: "{{ vault_remnawave_token }}"
  tasks:
    - name: Config profile is up to date
      kenyawest.remnawave.config_profile:
        name: default-profile
        config: "{{ lookup('ansible.builtin.file', 'files/xray-config.json') }}"

    - name: Squad exists
      kenyawest.remnawave.internal_squad:
        name: default-squad
        inbounds:
          - profile: default-profile
            tag: vless-reality

    - name: Node is registered and enabled
      kenyawest.remnawave.node:
        name: nl-ams-1
        state: enabled
        address: 203.0.113.10
        config_profile: default-profile
        inbounds: [vless-reality]

    - name: Users exist
      kenyawest.remnawave.user:
        username: "{{ item.username }}"
        expire_at: "{{ item.expire_at }}"
        traffic_limit: "{{ item.traffic_limit | default(omit) }}"
        internal_squads: [default-squad]
      loop:
        - { username: alice, expire_at: "2027-01-01T00:00:00Z", traffic_limit: 100GB }
        - { username: bob, expire_at: "2027-06-01T00:00:00Z" }
```

Run with `--check --diff` first to see what would change; the whole
collection, including the role, is usable in dry-run mode. A dry run against
a fresh panel also works: references to entities that would be created by
earlier tasks are shown by name in the predicted diff.

## Semantics worth knowing

- **Traffic limits** accept integers (bytes) or human-readable sizes
  (`100GB`, `1.5TB`). Suffix multiples are binary (1G = 1024^3), matching
  `ansible.builtin.human_to_bytes`. `0` means unlimited.
- **Timestamps** (`expire_at`) are compared as points in time, so
  `2027-01-01T00:00:00Z` and `2027-01-01T03:00:00+03:00` are the same value.
- **User status**: the panel derives `LIMITED` and `EXPIRED` itself for
  enabled users. `state: enabled` treats those as satisfied, so a user over
  quota does not flap between runs.
- **Clearing nullable string fields** (`tag`, `email`, `description`,
  `note`, ...) is done by setting them to an empty string.
- **`config_profile.config` is authoritative**: the panel's stored config is
  made exactly equal to what you supply.
- **Deleting is explicit**: the role and modules never remove entities that
  are simply absent from your variables; removal requires `state: absent`.

## What is intentionally not covered

Infra billing, node plugins and integrations, HWID device management, API
token management, passkeys, snippets and subscription page configs are not
modeled (yet). Of the bulk endpoints, only the host ones used by the node
cascade are. If you need something else, use the escape hatch:

```yaml
- name: Reset traffic for a user (non-idempotent action)
  kenyawest.remnawave.api:
    method: POST
    path: "/api/users/{{ user_id }}/actions/reset-traffic"
```

New resource modules are added when there is an actual configuration
management use case, not because an endpoint exists.

## Development and testing

The repository contains:

- `tests/unit/` - unit tests for the comparison/normalization helpers
  (`python3 -m unittest tests.unit.plugins.module_utils.test_common` with the
  collection tree on `PYTHONPATH`, or `ansible-test units`);
- `tests/mock/` - an in-memory mock of the Remnawave API and an end-to-end
  suite (`tests/mock/run.sh`) asserting check-mode behaviour, first-run
  changes, second-run idempotency, minimal-delta updates, and the whole
  node-to-linked-hosts cascade (`tests/mock/cascade.yml`);
- `docs/DESIGN.md` - the reasoning behind the resource model and the rules
  for adding new modules.

Sanity checks: `ansible-test sanity` from a checkout placed at
`.../ansible_collections/kenyawest/remnawave/`.

## License

GNU General Public License v3.0 or later. See `LICENSE`.
