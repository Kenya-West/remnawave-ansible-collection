# kenyawest.remnawave.remnawave

Applies a complete desired state to a [Remnawave](https://remna.st/) panel
from a set of variables, in one place and in dependency order.

The role is a thin, declarative wrapper over the collection's resource
modules. Everything the modules can do, the role can do; everything the role
does, it does by looping over those modules. If you only need to touch a
handful of entities, call the modules directly - the role earns its keep once
your panel state lives in inventory variables (group_vars, host_vars, a vault)
and you want a single `ansible-playbook` run to reconcile it.

## Table of contents

- [What the role does](#what-the-role-does)
- [Requirements](#requirements)
- [Role variables](#role-variables)
  - [Connection](#connection)
  - [Desired state](#desired-state)
- [Entry keys per stage](#entry-keys-per-stage)
- [Reading entities back](#reading-entities-back)
- [Usage](#usage)
  - [Minimal playbook](#minimal-playbook)
  - [Dry run first](#dry-run-first)
  - [State in inventory](#state-in-inventory)
  - [Managing only part of the panel](#managing-only-part-of-the-panel)
  - [Naming and identifiers](#naming-and-identifiers)
- [Examples](#examples)
  - [A complete panel from scratch](#a-complete-panel-from-scratch)
  - [Onboarding and offboarding users](#onboarding-and-offboarding-users)
  - [Decommissioning a node with its hosts](#decommissioning-a-node-with-its-hosts)
  - [Hosts driven by a list of domains](#hosts-driven-by-a-list-of-domains)
  - [Sharing defaults across many users](#sharing-defaults-across-many-users)
  - [Panel behind the Caddy custom-path protection](#panel-behind-the-caddy-custom-path-protection)
  - [Calling the panel without a reverse proxy](#calling-the-panel-without-a-reverse-proxy)
- [Behaviour worth knowing](#behaviour-worth-knowing)
- [Troubleshooting](#troubleshooting)
- [License and author](#license-and-author)

## What the role does

It runs one task per entity kind, always in this order, because each stage may
reference names created by the previous ones:

1. snippets (`remnawave_snippets`)
2. config profiles (`remnawave_config_profiles`)
3. internal squads (`remnawave_internal_squads`)
4. external squads (`remnawave_external_squads`)
5. nodes (`remnawave_nodes`)
6. hosts (`remnawave_hosts`)
7. users (`remnawave_users`)
8. subscription settings (`remnawave_subscription_settings`)
9. reading entities back (`remnawave_gather`), see
   [Reading entities back](#reading-entities-back)

Each stage is skipped when its variable is empty, which is the default. So a
play that sets only `remnawave_users` manages only users and never looks at
the rest of the panel.

The role manages only what you describe. Entities that exist on the panel but
are absent from your variables are left untouched; removing one is explicit -
keep its entry and set `state: absent`.

The role delegates nothing to the target host: the modules speak HTTP to the
panel URL, so the play normally runs on `localhost` (or on any host with
network access to the panel). Prefer `localhost`: against a remote host every
task goes over SSH, which costs seconds per task.

Hosts are applied in a single `kenyawest.remnawave.hosts` task rather than a
loop, so the stage reads the panel once however many hosts it declares, and a
bad entry fails it before any host is written.

## Requirements

- ansible-core 2.15 or newer, Python 3.9 or newer on the controller.
- Network access from the host running the play to the panel's HTTP API.
- A panel API token. Nothing is installed on the target; the role only makes
  API calls.

The modules use only the Python standard library - there are no collection
dependencies and no `pip install` step.

## Role variables

### Connection

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `remnawave_panel_url` | str | `''` | Base URL of the panel, for example `https://panel.example.com`. Required. |
| `remnawave_token` | str | `''` | Panel API token, sent as a bearer token. Required. Keep it in a vault. |
| `remnawave_api_key` | str | `''` | Value of the `X-Api-Key` header, only for panels behind the Caddy "security via custom path" setup. Empty means the header is not sent. |
| `remnawave_validate_certs` | bool | `true` | Whether TLS certificates are validated. |
| `remnawave_timeout` | int | `30` | Per-request timeout in seconds. |
| `remnawave_request_headers` | dict | `{}` | Extra HTTP headers added to every request. |

`remnawave_panel_url` and `remnawave_token` have no sensible defaults. You may
leave them unset if the environment variables `REMNAWAVE_PANEL_URL`,
`REMNAWAVE_TOKEN` and `REMNAWAVE_API_KEY` are exported for the process running
the play - the modules fall back to them.

### Desired state

| Variable | Type | Default | Items accept the options of |
| --- | --- | --- | --- |
| `remnawave_snippets` | list of dict | `[]` | `kenyawest.remnawave.snippet` |
| `remnawave_config_profiles` | list of dict | `[]` | `kenyawest.remnawave.config_profile` |
| `remnawave_internal_squads` | list of dict | `[]` | `kenyawest.remnawave.internal_squad` |
| `remnawave_external_squads` | list of dict | `[]` | `kenyawest.remnawave.external_squad` |
| `remnawave_nodes` | list of dict | `[]` | `kenyawest.remnawave.node` |
| `remnawave_hosts` | list of dict | `[]` | `kenyawest.remnawave.host` |
| `remnawave_users` | list of dict | `[]` | `kenyawest.remnawave.user` |
| `remnawave_subscription_settings` | dict | `{}` | `kenyawest.remnawave.subscription_settings` (a single entity, not a list) |
| `remnawave_gather` | dict | `{}` | Not desired state: which entities to read back afterwards. See [Reading entities back](#reading-entities-back). |

Within a list item, only the identifier is mandatory (`name`, `remark` or
`username`, or `inbound` for a config profile); every other key is optional
and simply not sent when omitted, which leaves that field alone on the panel.

## Entry keys per stage

The authoritative reference is `ansible-doc kenyawest.remnawave.<module>`.
The tables below are the same options, in the shape the role expects them.

**`remnawave_snippets`** - reusable configuration fragments that config
profiles embed. Applied first, so a profile referencing one finds it in place.

| Key | Type | Notes |
| --- | --- | --- |
| `name` | str | Required. Identifier. May contain `/` to group snippets into folders, for example `outbounds/warp`. |
| `state` | str | `present` (default) or `absent`. |
| `snippet` | list or JSON str | The fragment content. Authoritative: the panel's stored content is made exactly equal to it. Required when the snippet does not exist yet. |
| `sync` | str | `on_change` (default), `never` or `always`. Whether to push the snippet into the config profiles embedding it. `always` performs an action every run and therefore always reports `changed`. |

**`remnawave_config_profiles`** - Xray config profiles.

| Key | Type | Notes |
| --- | --- | --- |
| `name` | str | Identifier, unless `inbound` is set; then it renames the profile, and is required only to create it. One of `name` and `inbound` is required. |
| `inbound` | str | Tag of an inbound of the profile, which then identifies it instead of `name`. A `config` given alongside must still declare this inbound. |
| `state` | str | `present` (default) or `absent`. |
| `config` | dict or JSON str | The Xray configuration. Authoritative: the panel's stored config is made exactly equal to it. Required when the profile does not exist yet. |
| `tags` | list of str | Authoritative when set. See [tag format](#behaviour-worth-knowing). |

**`remnawave_internal_squads`** - squads users are assigned to.

| Key | Type | Notes |
| --- | --- | --- |
| `name` | str | Required. Identifier. |
| `state` | str | `present` (default) or `absent`. |
| `inbounds` | list | Authoritative when set. Each item is a plain inbound tag (or UUID), or `{tag: <inbound tag>, profile: <profile name>}` where `profile` is optional. Required when the squad does not exist yet. |
| `tags` | list of str | Tags of the squad itself, unrelated to the inbound `tag` above. Authoritative when set. |

**`remnawave_external_squads`** - external squads.

| Key | Type | Notes |
| --- | --- | --- |
| `name` | str | Required. Identifier. |
| `state` | str | `present` (default) or `absent`. |
| `tags` | list of str | Authoritative when set. |

**`remnawave_nodes`**

| Key | Type | Notes |
| --- | --- | --- |
| `name` | str | Required. Identifier; cannot be renamed through the role. |
| `state` | str | `present` (default), `enabled`, `disabled`, `absent`. |
| `linked_hosts` | str | `ignore` (default), `enable`, `disable`, `delete` - what to do with hosts bound to this node. |
| `address` | str | IP or DNS name. Required when the node does not exist yet. |
| `port` | int | Port of the node service. |
| `config_profile` | str | Config profile to activate, by name. Optional: it is the profile holding `inbounds`. |
| `inbounds` | list of str | Inbound tags to activate, all from one profile. Authoritative when set. Required at creation. |
| `traffic_tracking` | bool | Whether traffic tracking is active. |
| `traffic_limit` | int or str | Bytes, or a human-readable size such as `10TB`. |
| `notify_percent` | int | Percentage of the limit that triggers a notification. |
| `traffic_reset_day` | int | Day of month the node's statistics reset. |
| `country_code` | str | Two-letter code shown in the panel, or `XX` for none. |
| `consumption_multiplier` | float | Multiplier applied to user traffic on this node. |
| `tags` | list of str | Authoritative when set. |
| `note` | str | Free-form note; an empty string clears it. |

**`remnawave_hosts`** - entries of the subscription.

| Key | Type | Notes |
| --- | --- | --- |
| `identify_by` | str | `remark` (default) or `address` - which key identifies the host on the panel. |
| `remark` | str | The label shown in the client. Required, and the identifier, unless `identify_by: address`; then it is optional and renames the host. |
| `state` | str | `present` (default), `enabled`, `disabled`, `absent`. |
| `nodes` | list of str | Nodes the host is bound to, by name. Authoritative when set; an empty list unbinds it, and an unbound host is served from every node. |
| `config_profile` | str | Config profile the inbound belongs to. Optional: it is the profile holding `inbound`. |
| `inbound` | str | Inbound tag. Required at creation. |
| `address` | str | Address (domain or IP) advertised to clients. Required, and the identifier, with `identify_by: address`. |
| `port` | int | Port advertised to clients. |
| `path` | str | Path for path-based transports. |
| `sni` | str | TLS SNI. |
| `host_header` | str | HTTP `Host` header. |
| `alpn` | str | One of `h3`, `h2`, `http/1.1`, `h2,http/1.1`, `h3,h2,http/1.1`, `h3,h2`. |
| `fingerprint` | str | uTLS fingerprint, for example `chrome`. |
| `security_layer` | str | `default`, `tls` or `none`. |
| `hidden` | bool | Hide the host from subscriptions. |
| `tags` | list of str | Authoritative when set. |
| `server_description` | str | Free-form description. |
| `vless_route_id` | int | Route id the config profile's routing rules match on, 0-65535; an empty string clears it. |
| `override_sni_from_address` | bool | Derive the SNI from `address` instead of using `sni`. |
| `keep_sni_blank` | bool | Advertise an empty SNI. |
| `exclude_from_subscription_types` | list of str | Subscription types the host is left out of. Authoritative when set. |
| `internal_squads` | dict | `mode` (`exclude` or `allow_only`) and `squads` (names). The squad list is authoritative. |

Each host may appear once in `remnawave_hosts`. All entries are planned against
the panel as it was before the stage, so one entry cannot build on another's
change - for example, renaming a host and addressing it by the new remark in
the same run.

**`remnawave_users`**

| Key | Type | Notes |
| --- | --- | --- |
| `username` | str | Required. Identifier. |
| `state` | str | `present` (default), `enabled`, `disabled`, `absent`. |
| `expire_at` | str | ISO 8601 timestamp, for example `2027-01-01T00:00:00Z`. Required at creation. |
| `traffic_limit` | int or str | Bytes, or `100GB` / `1.5TB`. `0` means unlimited. |
| `traffic_limit_strategy` | str | `no_reset`, `day`, `week`, `month`, `month_rolling`. |
| `description` | str | Free-form; empty string clears it. |
| `tag` | str | Free-form; empty string clears it. |
| `email` | str | Empty string clears it. |
| `telegram_id` | int | Telegram user id. |
| `hwid_device_limit` | int | Maximum number of devices. |
| `internal_squads` | list of str | Squad names. Authoritative when set. |
| `external_squad` | str | External squad name; an empty string removes the user from any. |

**`remnawave_subscription_settings`** - a single dict, applied only when
non-empty.

| Key | Type | Notes |
| --- | --- | --- |
| `serve_json_at_base_subscription` | bool | |
| `show_custom_remarks` | bool | |
| `custom_remarks` | dict or JSON str | Shape defined by the panel. |
| `custom_response_headers` | dict | Headers returned with subscription responses. |
| `randomize_hosts` | bool | |
| `response_rules` | dict or JSON str | Shape defined by the panel. |
| `hwid_settings` | dict or JSON str | Shape defined by the panel. |

## Reading entities back

`remnawave_gather` makes the role read entities from the panel after the
management stages, and publish them as the `remnawave_gathered` fact for the
rest of the play. Reads never change anything, run under `--check` too, and
reflect the panel as this run left it. Set only `remnawave_gather` to use the
role purely for reading.

A kind is read when its key is present. Its value holds the options of the
matching info module; leave it empty (or `{}`) to read everything.

| Key | Options (of the module) | Published as |
| --- | --- | --- |
| `snippets` | `name` (`snippet_info`) | `remnawave_gathered.snippets` |
| `config_profiles` | `name` or `inbound` (`config_profile_info`) | `remnawave_gathered.config_profiles`, plus their inbounds with UUIDs and profile names as `remnawave_gathered.inbounds` |
| `internal_squads` | `name` (`internal_squad_info`) | `remnawave_gathered.internal_squads` |
| `external_squads` | `name` (`external_squad_info`) | `remnawave_gathered.external_squads` |
| `nodes` | `name` (`node_info`) | `remnawave_gathered.nodes` |
| `hosts` | `remark` or `address` (`host_info`) | `remnawave_gathered.hosts` |
| `users` | see below (`user_info`) | `remnawave_gathered.users`, plus `remnawave_gathered.users_page` |
| `subscription_settings` | none | `remnawave_gathered.subscription_settings` |
| `system` | `gather`, `timezone` (`system_info`) | `remnawave_gathered.system` |

Users are the only entities the panel can filter and paginate server-side,
through two endpoints with different query parameters. Which keys you use
decides the endpoint, and the two groups cannot be mixed:

| Keys | Endpoint |
| --- | --- |
| `username`, `id`, `short_uuid` | A single user. |
| `status` (`active`, `disabled`, `limited`, `expired`), `traffic_limit_strategy`, `telegram_id`, `email`, `tag`, `external_squad` (name or UUID), `cursor` | `/api/users/stream`, cursor-paginated. |
| `filters` (list of `{id, value}`), `filter_modes` (dict of field to mode), `global_filter_mode`, `sorting` (list of `{id, desc}`), `start` | `/api/users`, offset-paginated. The panel warns these filters are expensive. |

Without `size`, `start` or `cursor` every page is fetched. With any of them
one page is returned, and `remnawave_gathered.users_page` carries `total`
(table endpoint) or `next_cursor` and `has_more` (stream endpoint).

```yaml
- name: Apply the users, then report who is over quota
  hosts: localhost
  gather_facts: false
  roles:
    - role: kenyawest.remnawave.remnawave
      vars:
        remnawave_users: "{{ team }}"
        remnawave_gather:
          users:
            status: limited
          nodes:
  post_tasks:
    - name: Over-quota users
      ansible.builtin.debug:
        msg: "{{ remnawave_gathered.users | map(attribute='username') | list }}"
```

## Usage

### Minimal playbook

```yaml
---
- name: Reconcile the Remnawave panel
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - role: kenyawest.remnawave.remnawave
      vars:
        remnawave_panel_url: https://panel.example.com
        remnawave_token: "{{ vault_remnawave_token }}"
        remnawave_users:
          - username: alice
            expire_at: "2027-01-01T00:00:00Z"
```

### Dry run first

The whole role supports check and diff mode. Nothing is written to the panel
under `--check`, and the predicted changes are printed field by field:

```console
$ ansible-playbook remnawave.yml --check --diff
```

A dry run against an empty panel also works: entities that would be created by
an earlier stage are referenced by name in the later stages' predicted diff
rather than failing to resolve.

Running the play twice in a row must report `changed=0` the second time. If it
does not, the differing field is visible in `--diff` output - that is a bug
worth reporting.

### State in inventory

In practice the variables belong in `group_vars`, not inline in the play, so
the panel's desired state is reviewable in version control and the play stays
one line:

```
inventory/
  group_vars/
    remnawave/
      connection.yml       # panel URL, non-secret settings
      vault.yml            # ansible-vault: token, api key
      profiles.yml         # remnawave_config_profiles, remnawave_internal_squads
      topology.yml         # remnawave_nodes, remnawave_hosts
      users.yml            # remnawave_users
```

```yaml
---
- name: Reconcile the Remnawave panel
  hosts: remnawave
  gather_facts: false
  roles:
    - kenyawest.remnawave.remnawave
```

### Managing only part of the panel

Because empty variables mean "manage nothing of this kind", you can split the
work across plays or tag them. To reconcile users alone, set only
`remnawave_users`; the node, host and profile stages loop over empty lists and
report `ok=0`.

To run one stage of a fully populated variable set, use `--limit` on the data
rather than on the role: for example define the users play separately, or pass
`-e '{"remnawave_nodes": []}'` on a one-off run.

### Naming and identifiers

Entities are addressed by stable human identifiers: node `name`, host
`remark`, user `username`, squad `name`, and profile `name` or the `inbound`
tag of one of its inbounds. Cross-references (`config_profile`, `inbounds`,
`internal_squads`, `nodes`) are given by name or tag and resolved to UUIDs
internally, so UUIDs never need to appear in your variables. Inbound tags are
unique across profiles, so wherever an inbound is referenced, its config
profile may be left out.

```yaml
remnawave_config_profiles:
  # whatever the profile holding vless-reality is called, tag it
  - inbound: vless-reality
    tags: [PRODUCTION]
``` Changing an identifier is not a rename - the role will create a new
entity and leave the old one, so rename in the panel or delete explicitly.

## Examples

### A complete panel from scratch

```yaml
---
- name: Apply the full Remnawave desired state
  hosts: localhost
  connection: local
  gather_facts: false
  vars:
    remnawave_panel_url: https://panel.example.com
    remnawave_token: "{{ vault_remnawave_token }}"

    remnawave_snippets:
      - name: outbounds/warp
        snippet: "{{ lookup('ansible.builtin.file', 'files/warp-outbound.json') }}"

    remnawave_config_profiles:
      - name: default-profile
        config: "{{ lookup('ansible.builtin.file', 'files/xray-config.json') }}"

    remnawave_internal_squads:
      - name: default-squad
        inbounds:
          - profile: default-profile
            tag: vless-reality

    remnawave_external_squads:
      - name: resellers

    remnawave_nodes:
      - name: nl-ams-1
        state: enabled
        address: 203.0.113.10
        port: 2222
        config_profile: default-profile
        inbounds: [vless-reality]
        country_code: NL
        tags: [PRODUCTION, EU]
      - name: de-fra-1
        state: enabled
        address: 203.0.113.20
        config_profile: default-profile
        inbounds: [vless-reality]
        country_code: DE
        consumption_multiplier: 1.5

    remnawave_hosts:
      - remark: Amsterdam
        state: enabled
        config_profile: default-profile
        inbound: vless-reality
        address: ams.example.com
        port: 443
        sni: ams.example.com
        fingerprint: chrome
        security_layer: tls
        nodes: [nl-ams-1]
      - remark: Frankfurt
        state: enabled
        config_profile: default-profile
        inbound: vless-reality
        address: fra.example.com
        port: 443
        sni: fra.example.com
        fingerprint: chrome
        nodes: [de-fra-1]

    remnawave_users:
      - username: alice
        state: enabled
        expire_at: "2027-01-01T00:00:00Z"
        traffic_limit: 100GB
        traffic_limit_strategy: month
        internal_squads: [default-squad]

    remnawave_subscription_settings:
      randomize_hosts: true

  roles:
    - kenyawest.remnawave.remnawave
```

The config profile is given here through a file lookup, which keeps the Xray
JSON editable on its own. An inline dict works equally well - see
`tests/mock/play.yml` in this repository for that form.

### Onboarding and offboarding users

Both are the same declaration; only `state` differs. Nothing is ever deleted
implicitly, so an offboarded user stays in the variables until you are ready to
drop the entry:

```yaml
remnawave_users:
  # new hire
  - username: carol
    state: enabled
    expire_at: "2027-06-01T00:00:00Z"
    traffic_limit: 200GB
    traffic_limit_strategy: month
    internal_squads: [default-squad]
    email: carol@example.com

  # on leave - keep the account, deny access
  - username: bob
    state: disabled

  # left the company - remove from the panel
  - username: dave
    state: absent
```

Note that `state: present` deliberately does not touch the enabled/disabled
status. A user disabled in the panel stays disabled across role runs unless you
declare `state: enabled`.

### Decommissioning a node with its hosts

A node's subscription hosts should not outlive it. Rather than disabling each
host by hand, let the node carry them along with `linked_hosts`:

```yaml
remnawave_nodes:
  - name: nl-ams-1
    state: disabled
    linked_hosts: disable

remnawave_hosts:
  # present, so the host stage does not re-enable what the cascade disabled
  - remark: Amsterdam
    state: present
    nodes: [nl-ams-1]
```

`linked_hosts` accepts `ignore` (default), `enable`, `disable` and `delete`,
and applies only to hosts **explicitly bound** to the node through their
`nodes` list. A host bound to no node is served from every node, so a single
node going away never touches it.

Putting the node back into service is symmetrical:

```yaml
remnawave_nodes:
  - name: nl-ams-1
    state: enabled
    linked_hosts: enable
```

Retiring it for good, hosts included - the hosts are handled before the node is
deleted, while the binding can still be resolved:

```yaml
remnawave_nodes:
  - name: nl-ams-1
    state: absent
    linked_hosts: delete

remnawave_hosts: []   # or drop the host entries entirely
```

The important detail is the host's `state`. If you declare a host as `enabled`
while the node cascade disables it, the two fight and every run reports a
change: the node stage disables the host, the host stage re-enables it. Declare
such hosts as `present`.

### Hosts driven by a list of domains

When your source data is a list of domains rather than a list of display
names, set `identify_by: address` and let the entries be keyed by the domain.
The remark of a newly created host then defaults to its address, so nothing
has to invent one:

```yaml
vars:
  _host_defaults: &host_defaults
    identify_by: address
    state: enabled
    config_profile: default-profile
    inbound: vless-reality
    port: 443
    fingerprint: chrome
    nodes: [nl-ams-1]          # the node already exists

  remnawave_hosts:
    - <<: *host_defaults
      address: ams.example.com
      sni: ams.example.com
    - <<: *host_defaults
      address: fra.example.com
      sni: fra.example.com
    - <<: *host_defaults
      address: waw.example.com
      sni: waw.example.com
```

If the domain list is genuinely dynamic, do not try to build the role
variable with a Jinja loop - a `{%- for -%}` block in a vars file produces a
string, not a list. Drive the module directly instead, which is what the role
does internally anyway:

```yaml
- name: One host per domain, all sharing the same settings
  kenyawest.remnawave.host:
    identify_by: address
    address: "{{ item }}"
    sni: "{{ item }}"
    state: enabled
    config_profile: default-profile
    inbound: vless-reality
    port: 443
    fingerprint: chrome
    nodes: [nl-ams-1]
  loop: "{{ host_domains }}"
```

Retiring some of those domains is the same list with a different `state`, and
has nothing to do with the node cascade:

```yaml
remnawave_hosts:
  - identify_by: address
    address: fra.example.com
    state: disabled
  - identify_by: address
    address: waw.example.com
    state: absent
```

One caveat: an address is not unique in Remnawave - the same domain can serve
several inbounds or ports. The role fails rather than guessing when an address
matches more than one host, naming the candidates. Use the `host_info` module
to see them, and address those hosts by `remark`:

```yaml
- name: Which hosts serve these domains
  kenyawest.remnawave.host_info:
    address: "{{ item }}"
  loop: "{{ retired_domains }}"
  register: matched

- name: Disable every one of them, whatever its remark
  kenyawest.remnawave.host:
    remark: "{{ item.remark }}"
    state: disabled
  loop: "{{ matched.results | map(attribute='hosts') | flatten }}"
  loop_control:
    label: "{{ item.remark }}"
```

### Sharing defaults across many users

The variables are ordinary data, so keeping a long user list readable is a YAML
problem, not an Ansible one. YAML anchors handle it without any templating -
keys written in the entry itself override the merged ones:

```yaml
vars:
  # not a role variable, just a YAML anchor to merge from
  _user_defaults: &user_defaults
    state: enabled
    traffic_limit: 100GB
    traffic_limit_strategy: month
    internal_squads: [default-squad]

  remnawave_users:
    - <<: *user_defaults
      username: alice
      expire_at: "2027-01-01T00:00:00Z"

    - <<: *user_defaults
      username: bob
      expire_at: "2027-06-01T00:00:00Z"

    - <<: *user_defaults
      username: carol
      expire_at: "2027-06-01T00:00:00Z"
      traffic_limit: 500GB          # overrides the merged default
```

If the source of truth is a compact list somewhere else, expand it with
`combine`. Mind the argument order - the right-hand dict wins, so
`map('combine', defaults)` makes the *defaults* override each entry, which is
rarely what you want:

```yaml
vars:
  remnawave_user_defaults:
    state: enabled
    traffic_limit: 100GB
    traffic_limit_strategy: month
    internal_squads: [default-squad]

  team:
    - username: alice
      expire_at: "2027-01-01T00:00:00Z"
    - username: bob
      expire_at: "2027-06-01T00:00:00Z"
      traffic_limit: 500GB

  remnawave_users: >-
    {{ team | map('ansible.builtin.combine', remnawave_user_defaults) | list }}
```

So use that form only for keys no entry overrides. Once entries need to win
over the defaults, the YAML anchors above - or simply writing the entries out
in full - are the better answer. There is no prize for a clever vars file; the
role reads whatever list you hand it.

### Panel behind the Caddy custom-path protection

If your panel uses the [security via custom path](https://docs.rw/security/caddy-with-custom-path)
setup, the extra header is a single variable:

```yaml
remnawave_panel_url: https://panel.example.com
remnawave_token: "{{ vault_remnawave_token }}"
remnawave_api_key: "{{ vault_remnawave_api_key }}"
```

### Calling the panel without a reverse proxy

When you reach the panel directly on its own port, Remnawave expects the
forwarding headers a proxy would normally add:

```yaml
remnawave_request_headers:
  X-Forwarded-For: 127.0.0.1
  X-Forwarded-Proto: https
```

### Verifying credentials before a big run

The role has no preflight check of its own; the `system_info` module doubles as
one and costs a single request:

```yaml
- name: Panel is reachable and the token works
  kenyawest.remnawave.system_info:
    panel_url: "{{ remnawave_panel_url }}"
    token: "{{ remnawave_token }}"
  register: remnawave_health

- name: Apply the desired state
  ansible.builtin.include_role:
    name: kenyawest.remnawave.remnawave
```

## Behaviour worth knowing

- **Idempotency.** Each stage reads the current state, compares only the fields
  you set, and sends the minimal update. A second run reports `changed=0`.
- **Omitted means unmanaged.** Keys you do not set are not sent, so fields
  configured in the panel UI survive role runs. This is what makes partial
  adoption safe.
- **Lists are authoritative when set.** `inbounds`, `internal_squads`, `tags`
  and `nodes` replace whatever is there rather than merging. Setting one to an
  empty list clears it.
- **Tags** can be set on config profiles, internal and external squads, nodes
  and hosts - up to 10 per entity, each at most 36 characters of uppercase
  letters, digits, `_` and `:` (for example `REGION:EU`). A tag outside that
  format fails the task before anything is sent; tags are not uppercased for
  you. Users are the exception: the panel gives them a single `tag` string
  (up to 16 characters, no `:`), not a list.
- **Clearing string fields** (`note`, `tag`, `email`, `description`,
  `server_description`) is done with an empty string, not with `null`.
- **Traffic sizes** accept bytes as an integer or a human-readable string
  (`100GB`, `1.5TB`). Multiples are binary (1G = 1024^3), matching
  `ansible.builtin.human_to_bytes`. `0` means unlimited.
- **Timestamps** are compared as points in time, so
  `2027-01-01T00:00:00Z` and `2027-01-01T03:00:00+03:00` are the same value and
  do not produce a spurious change.
- **User status.** The panel derives `LIMITED` (over quota) and `EXPIRED`
  itself. `state: enabled` treats those as already satisfied instead of forcing
  the user back to `ACTIVE`, which the panel would undo on its next pass.
- **`config` and `snippet` are authoritative.** A config profile's stored Xray
  config, and a snippet's stored content, are made exactly equal to what you
  supply; anything edited in the panel UI is overwritten.
- **Snippets sync themselves.** Changing a snippet does not by itself reach the
  config profiles embedding it, so the snippet stage runs the panel's sync
  action whenever it changed something. Set `sync: never` on an entry to defer
  that, or `sync: always` to force it - the latter is an action, so it reports
  `changed` on every run.
- **Nothing is deleted implicitly.** Removing an entry from the variables stops
  managing that entity, it does not remove it from the panel.
- **Secrets.** `remnawave_token` and `remnawave_api_key` are credentials; keep
  them in `ansible-vault` or supply them through the `REMNAWAVE_TOKEN` and
  `REMNAWAVE_API_KEY` environment variables and leave the variables unset.

## Troubleshooting

**A run reports changes every time.** Look at `--diff` for the field that keeps
flipping. The usual cause is a host declared `enabled` while a node's
`linked_hosts: disable` cascade disables it in the same play; declare the host
`state: present`. Otherwise it is a normalization bug - the diff output names
the field.

**"not found" for a config profile, squad or inbound.** The reference is
resolved by name or tag against what exists on the panel at that moment. Check
the spelling, and make sure the referenced entity is declared in this role run
(earlier stages create it before later stages resolve it) or already exists.

**Authentication failures.** Confirm the token with the `system_info` module.
If the panel sits behind the Caddy custom-path setup, `remnawave_api_key` is
required as well; if you reach the panel directly on its port, add the
`X-Forwarded-*` headers shown above.

**TLS errors.** For a panel with a self-signed certificate, prefer adding the
CA to the controller's trust store over setting
`remnawave_validate_certs: false`.

**Something the role does not model.** The role covers the resources listed
above and nothing else by design. For anything else - imperative actions such
as resetting traffic, or endpoints with no persistent desired state - use the
`kenyawest.remnawave.api` escape-hatch module in your own task, outside the
role.

## License and author

GNU General Public License v3.0 or later. See `LICENSE` at the root of the
collection.

Kenya-West (@Kenya-West).
