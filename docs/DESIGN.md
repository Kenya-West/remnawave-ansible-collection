# Design notes

This document records the decisions behind the collection so that future
changes stay consistent with them.

## Resources, not endpoints

The Remnawave API (v3.4.3) exposes 161 paths across roughly 28 controllers.
Its conceptual resource model is far smaller: users, nodes, hosts, config
profiles, snippets, squads, and a handful of settings singletons. The collection maps
Ansible modules to that resource model, not to the endpoint list.

Consequences:

- One module may call several endpoints. `node` uses list/create/update/
  delete, the enable/disable action endpoints and the host bulk endpoints,
  all behind `state` and `linked_hosts`.
- Most endpoints are not exposed at all. Statistics, billing, plugins and
  similar controllers have no module. The API may gain endpoints without the
  collection needing a release.
- The public contract of the collection is its module options, which are
  Ansible-flavored (snake_case, human units, names instead of UUIDs) and
  deliberately decoupled from the DTO field names. Renamed or reshaped DTOs
  are absorbed in `module_utils`, not in playbooks.

## Layering

- `module_utils/client.py` - transport only: auth headers (bearer token and
  the Caddy `X-Api-Key`), JSON, the `{"response": ...}` envelope, error
  translation. Contains no knowledge of any resource.
- `module_utils/resources.py` - finders and name-to-UUID resolution. All
  panel lookups shared between modules live here.
- `module_utils/common.py` - the desired/current comparison engine
  (`FieldSpec`, `build_patch`), value normalization (sizes, timestamps,
  sets), the common argument spec, and check-mode helpers.
- `plugins/modules/*` - one file per resource; mostly declarative field
  tables plus the create/update/delete choreography.

## Idempotency rules

- Only options the user sets are compared and patched (PATCH semantics).
  Omitted options are never sent, so server-side values survive.
- Comparison happens on normalized values: timestamps as instants, scalar
  lists as sets, enum-like strings uppercased, `""` mapped to `null` for
  nullable string fields.
- Server-derived values must not cause flapping. Example: user status
  `LIMITED`/`EXPIRED` is treated as satisfying `state: enabled`, because the
  panel computes those states itself and would immediately restore them.
- Authoritative-versus-partial is decided per field, not copied from the
  API: `config_profile.config`, squad `inbounds` and all list options are
  authoritative when set; everything else is partial.

## One state property, not a bag of flags

`user`, `node` and `host` express existence *and* enabled-ness through the
single well-known `state` option (`present`, `enabled`, `disabled`,
`absent`) rather than a `state` plus a separate `enabled` boolean. Two
options for one concept invite contradictory playbooks (`state: absent` with
`enabled: true`), and `present` is the useful third position that a boolean
cannot express: "must exist, and I am not the one deciding whether it is
enabled".

Underneath, the three resources implement it differently - nodes and users
have dedicated action endpoints, a host has an `isDisabled` field - which is
exactly the sort of API detail the module layer is there to hide.

## Identifiers can be chosen, but never guessed

A resource has one stable human identifier, except where the panel offers no
single natural one. Hosts are the case in point: the display name (`remark`)
suits panels curated by hand, while deployments generated from a domain list
have no remark to speak of and would have to invent one. `host` therefore
takes `identify_by` (`remark`, the default, or `address`), and the option not
in use becomes an ordinary managed field - which is how a host found by its
domain can be renamed.

What does not change is the rule that ambiguity is an error. Remarks are
unique in practice; addresses are not, since one domain can serve several
inbounds or ports. An identifier matching more than one host fails the task
and names the candidates rather than picking one, because silently
reconfiguring an arbitrary member of a set is worse than stopping.
`host_info` is the escape valve: it filters by remark or address, returns
every match, and lets the playbook decide.

## Cascades are opt-in and narrow

`node` can carry the hosts bound to it along when the node is disabled or
deleted (`linked_hosts`). The rules that keep this safe:

- It is off by default. Nothing cascades unless the playbook asks.
- Only hosts *explicitly* bound to the node are touched. A host bound to no
  node is served from every node; treating it as belonging to whichever node
  is being removed would silently break the whole panel's subscriptions.
- On deletion the hosts are handled before the node, because the binding
  lives on the host and is resolved through the node's UUID. Once the node
  is gone the link is unrecoverable, so a cascade against an already deleted
  node does nothing rather than guessing.
- The affected hosts are returned (`linked_hosts`) and predicted in check
  mode, so a dry run shows exactly what a decommission would take with it.

Everything else stays out of the resource modules: this is a real
configuration-management relationship (a host bound to a node cannot serve
traffic once that node is gone), not a general "delete related objects"
framework.

## Check mode

Every module supports check mode and diff mode. Two specifics:

- Write modules compute the same patch as in a real run and report
  `changed`/`diff` without performing the request.
- On a fresh panel, later resources may reference entities (profiles,
  squads) that earlier check-mode tasks did not actually create. Resolution
  failures are tolerated in check mode only: the human-readable names are
  used as placeholders in the predicted diff (`resolve_for_check_mode`).
  In a real run the same situation fails loudly.

## Actions are not configuration

Endpoints like reset-traffic, restart, revoke-subscription describe events,
not state; a `reset_traffic: true` option would fire on every run. They are
intentionally left to the `api` escape-hatch module, and their
non-idempotence is the caller's to handle (`changed_when`, conditions).

The exception is an action that *completes* a state change rather than
standing on its own. Syncing a snippet is one: the panel stores snippet
content and the config profiles embedding it separately, so a snippet
updated without a sync is only half-applied, and no playbook wants that as
its resting state. `snippet` therefore runs the sync itself, but only when
it actually changed the content (`sync: on_change`), which keeps a
converged run a no-op. The two escapes are explicit: `never`, to update a
batch and sync once afterwards, and `always`, which is a real action and is
documented as always reporting `changed`.

The test for whether an action belongs in a resource module is this: would
leaving it out make the module's own change incomplete? Restarting a node
is not in that category; syncing a snippet you just rewrote is.

## Versioning policy

The collection is versioned semantically and pins a tested Remnawave API
range in the README rather than promising universal compatibility. This
mirrors Remnawave's own practice: its official SDK maps contract versions to
panel versions. When the panel API changes incompatibly, the collection
absorbs what it can in `module_utils` and otherwise raises its major
version.

## Adding a new module

Checklist:

1. There is a real configuration management use case (not merely a new
   endpoint).
2. Identification by a stable human identifier; fail on ambiguity.
3. `state` (`present`/`absent`, plus `enabled`/`disabled` when the resource
   can be switched off), check mode, diff mode, `changed=false` on rerun.
4. Field table via `FieldSpec` with explicit normalization per field; decide
   authoritative vs partial per field.
5. Name/tag resolution for any cross-references.
6. Extend the mock panel and `tests/mock/play.yml` so the idempotency suite
   covers the new resource, and add the module to the `remnawave` action
   group in `meta/runtime.yml` plus, when appropriate, to the role.
7. Any relationship that cascades gets its own scenario in
   `tests/mock/cascade.yml`, including the case that must *not* be touched.
8. If the API needs a follow-up action for the change to take effect, run
   it from the module on change rather than leaving it to the caller, and
   give the playbook a way to opt out - see snippet syncing above.
