# Contributing to kenyawest.remnawave

This document covers day-to-day development, testing, versioning and
release/publishing. For the reasoning behind the module design (why
resources instead of endpoints, layering, idempotency rules), see
[docs/DESIGN.md](docs/DESIGN.md) - read it before adding a module.

## Getting set up

The collection must live at
`<something>/ansible_collections/kenyawest/remnawave` for Ansible to find
it. The simplest way is to clone (or symlink) the checkout into place:

```bash
mkdir -p ~/dev/collections/ansible_collections/kenyawest
ln -s ~/dev/remnawave-ansible-collection ~/dev/collections/ansible_collections/kenyawest/remnawave
export ANSIBLE_COLLECTIONS_PATH=~/dev/collections
```

Requirements: Python 3.9+, [`uv`](https://docs.astral.sh/uv/), `ansible-core`
(any version in 2.15-2.18; CI matrices 2.16-2.18). Modules use only the
Python standard library, so no extra runtime dependencies.

```bash
uv venv
source .venv/bin/activate
uv pip install ansible-core
```

To pin the same ansible-core version CI uses for a given job, e.g.:

```bash
uv pip install "ansible-core~=2.18.0"
```

Activate the venv (`source .venv/bin/activate`) in each new shell before
running the commands below - they assume `ansible-test`, `ansible-playbook`
and `python3` resolve from it.

## Repository layout

- `plugins/modules/` - one file per resource (`user`, `node`, `host`,
  `config_profile`, `internal_squad`, `external_squad`,
  `subscription_settings`, `api`, plus each resource's `*_info` module).
- `plugins/module_utils/`
  - `client.py` - HTTP transport, auth, error translation only.
  - `resources.py` - finders and name-to-UUID resolution shared across
    modules.
  - `common.py` - the desired/current comparison engine (`FieldSpec`,
    `build_patch`), value normalization, the common argument spec.
- `roles/remnawave/` - the role that loops over desired-state variables and
  calls the modules.
- `tests/unit/` - unit tests for `module_utils`.
- `tests/mock/` - an in-memory mock Remnawave panel plus an end-to-end
  Ansible playbook suite run against it.
- `docs/DESIGN.md` - design rationale and rules for adding modules.
- `changelogs/` - changelog fragments (see Versioning below).
- `meta/runtime.yml` - `requires_ansible` and the `remnawave` action group.
- `galaxy.yml` - collection namespace, name, version and metadata.

## Running the tests

**Unit tests** (comparison/normalization helpers):

```bash
PYTHONPATH=~/dev/collections python3 -m unittest tests.unit.plugins.module_utils.test_common -v
```

or, from inside the collection checkout at its `ansible_collections/...`
path:

```bash
ansible-test units
```

**Mock integration suite** - spins up an in-memory mock of the Remnawave
API and runs a playbook against it, asserting check-mode predictions,
first-run changes, second-run idempotency, minimal-delta updates, and the
node -> linked-hosts cascade:

```bash
tests/mock/run.sh
```

This must be run with the checkout reachable via
`ANSIBLE_COLLECTIONS_PATH` as `.../ansible_collections/kenyawest/remnawave`
(see Getting set up above).

**Sanity checks** (from the `ansible_collections/kenyawest/remnawave` path):

```bash
ansible-test sanity --docker default -v
```

All three run in CI on every push and pull request to `master`
(`.github/workflows/ci.yml`), across ansible-core 2.16, 2.17 and 2.18 for
sanity. Run them locally before opening a PR.

## Adding or changing a module

New resource modules are added when there is an actual configuration
management use case, not because an API endpoint exists - see
[docs/DESIGN.md](docs/DESIGN.md#resources-not-endpoints). Before adding
one:

1. Confirm the resource maps to something a user declares desired state
   for, not a one-off action or a statistics endpoint.
2. Follow the existing layering: transport-only code in `client.py`,
   lookups in `resources.py`, comparison/normalization in `common.py`, and
   keep the module itself mostly a declarative field table plus
   create/update/delete choreography.
3. Support check mode and diff mode, and add the module to the
   `remnawave` action group in `meta/runtime.yml`.
4. Add unit coverage for any new normalization/comparison logic, and
   extend the mock panel (`tests/mock/`) with the scenarios needed to
   exercise the new module end to end.
5. Update `README.md` (module list, examples) and add a changelog
   fragment (see below).

## Versioning

The collection follows semantic versioning against its own module
interface, not the Remnawave API version. The API version it was
developed and tested against is stated in `README.md` and in the release's
changelog entry - a new collection release states any change to that
supported range.

To cut a new version:

1. **Bump `version` in [galaxy.yml](galaxy.yml).** This is the single
   source of truth for the collection version.
2. **Add a changelog fragment** for each user-facing change under
   `changelogs/fragments/` (create the directory if it doesn't exist yet),
   e.g. `changelogs/fragments/add-foo-module.yml`:

   ```yaml
   minor_changes:
     - foo - add support for bar (https://github.com/Kenya-West/remnawave-ansible-collection/issues/NN).
   ```

   Valid sections: `major_changes`, `minor_changes`, `breaking_changes`,
   `deprecated_features`, `removed_features`, `security_fixes`, `bugfixes`,
   `known_issues`. New modules and roles don't need a fragment - they're
   picked up automatically from `plugins/modules/*` and `roles/*` by their
   docstrings.
3. **Regenerate `CHANGELOG.rst`** with `antsibull-changelog`, run via `uvx`
   (no install needed):

   ```bash
   uvx antsibull-changelog release
   ```

   This consumes the fragments, rewrites `CHANGELOG.rst` **from scratch**
   out of `changelogs/changelog.yaml` (every past release plus the new
   one), and deletes the fragments it just consumed.
   `changelogs/config.yaml`, `changelogs/changelog.yaml` and
   `changelogs/.plugin-cache.yaml` are committed, not gitignored - the
   `release` command errors out (`Only the 'init' command can be used ...
   without changelogs/config.yaml`) if `config.yaml` is missing, and if
   `changelog.yaml` doesn't already contain a release's data, that
   release's section is gone from the regenerated `CHANGELOG.rst`, even
   if it was hand-written before. Both files already exist in this repo,
   so day-to-day releases just need step 3 above. (They were bootstrapped
   once with `uvx antsibull-changelog init .`, then `changelogs/changelog.yaml`
   was hand-seeded with the pre-existing v0.1.0 entry before the first
   `release` run, so history wasn't lost - see git history on those files
   if you need to do this again for another repo.)
4. Commit the version bump and changelog together, tag the commit
   (`git tag vX.Y.Z`), and push the tag.

Version bump rules of thumb: patch for bugfixes with no option changes,
minor for new modules/options that are backward compatible, major for
breaking changes to existing module options or behavior.

## Publishing

### GitHub

1. Make sure `master` is green in CI and the version/changelog steps above
   are committed and tagged.
2. Push the tag: `git push origin vX.Y.Z`.
3. Create a GitHub Release from that tag (`gh release create vX.Y.Z --generate-notes`
   or via the UI), pasting the new `CHANGELOG.rst` section into the
   release notes.

### Ansible Galaxy

There is no publish-on-tag automation yet, so publishing is a manual step
after the GitHub release:

1. Build the tarball from the collection root (`ansible-galaxy` ships as
   part of `ansible-core`, installed above via `uv`):

   ```bash
   ansible-galaxy collection build
   ```

   This produces `kenyawest-remnawave-X.Y.Z.tar.gz`, respecting the
   `build_ignore` list in `galaxy.yml` (excludes `remnawave-api.yaml`,
   `tests/output`, editor/history directories, etc.).

2. Publish it:

   ```bash
   ansible-galaxy collection publish kenyawest-remnawave-X.Y.Z.tar.gz --api-key <your-galaxy-api-key>
   ```

   The API key is generated from your Ansible Galaxy account
   (Preferences -> API Key) and should be passed via `--api-key` or the
   `ANSIBLE_GALAXY_API_KEY` environment variable, never committed to the
   repo.

3. Verify the new version appears at
   `https://galaxy.ansible.com/ui/repo/published/kenyawest/remnawave/`.

Do not publish to Galaxy before the corresponding GitHub tag/release
exists - the two should always point at the same commit.

## Pull requests

- Keep PRs scoped to one resource or concern.
- Run the unit tests and the mock integration suite locally before
  opening a PR; CI re-runs both plus sanity checks.
- Include a changelog fragment for any user-facing change (see
  Versioning above) - this is what CI and the release process expect,
  not a version bump in the PR itself. Version bumps happen at release
  time, not per-PR.
