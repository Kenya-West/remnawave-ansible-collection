# remnawave role

Applies a complete desired state to a Remnawave panel, in dependency order:

1. config profiles
2. internal squads
3. external squads
4. nodes
5. hosts
6. users
7. subscription settings

Each stage loops over a list variable whose items accept the options of the
corresponding module of this collection (`kenyawest.remnawave.config_profile`,
`internal_squad`, `external_squad`, `node`, `host`, `user`); consult
`ansible-doc` for the full option lists. The whole role supports `--check`
and `--diff`.

The role manages only what you describe. Entities absent from the variables
are left alone; to remove one, keep its entry and set `state: absent`.

Nodes, hosts and users accept `state: present` (exists, enabled/disabled
status left alone), `enabled`, `disabled` and `absent`. A node entry may
also carry `linked_hosts: ignore|enable|disable|delete` to carry the hosts
bound to it along when the node is disabled or deleted; see the
`kenyawest.remnawave.node` module documentation. When a host's status is
driven by that cascade, declare the host with `state: present` so the host
task does not immediately undo it.

## Variables

Connection (required unless the corresponding `REMNAWAVE_*` environment
variables are set for the modules):

```yaml
remnawave_panel_url: https://panel.example.com
remnawave_token: "{{ vault_remnawave_token }}"
# Only for panels behind the Caddy security-via-custom-path setup:
remnawave_api_key: "{{ vault_remnawave_api_key }}"

remnawave_validate_certs: true
remnawave_timeout: 30
remnawave_request_headers: {}
```

Desired state (all default to empty, meaning "manage nothing of this kind"):

```yaml
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
    address: 203.0.113.10
    port: 2222
    config_profile: default-profile
    inbounds: [vless-reality]
    state: enabled
    country_code: NL

remnawave_hosts:
  - remark: Amsterdam
    config_profile: default-profile
    inbound: vless-reality
    address: ams.example.com
    port: 443
    sni: ams.example.com
    fingerprint: chrome
    # Bind the host to nodes so the node cascade can carry it along.
    nodes: [nl-ams-1]

remnawave_users:
  - username: alice
    # state: present | enabled | disabled | absent
    expire_at: "2027-01-01T00:00:00Z"
    traffic_limit: 100GB
    traffic_limit_strategy: month
    internal_squads: [default-squad]
  - username: old-user
    state: absent

remnawave_subscription_settings:
  randomize_hosts: true
```

## Decommissioning a node

Set the node's entry to `disabled` (or `absent`) and let it carry the hosts
bound to it along:

```yaml
remnawave_nodes:
  - name: nl-ams-1
    state: disabled
    linked_hosts: disable

remnawave_hosts:
  - remark: Amsterdam
    # present, so the host task does not re-enable what the cascade disabled
    state: present
    nodes: [nl-ams-1]
```

## Example playbook

```yaml
- hosts: localhost
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
