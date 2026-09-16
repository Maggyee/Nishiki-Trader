# Inactive installation bundle and fixed check entry

The existing-IPv4 implementation now has an executable, reviewable installation
bundle and a fixed installed **read-only check**. The previous
[installation report](portfolio-egress-installation-2026-09-16.md) and v1 contract
remain historical. The [v2 review contract](portfolio-egress-installation-contract-2026-09-16-v2.json)
pins the four installed source hashes, installer and actual archive. No host
installation, account creation, collector launch or venue request occurred.

## Concrete artifact

Two independent isolated-Python builds produced identical bytes:

- `data/egress-installation-bundle-2026-09-16.tar`
- `data/egress-installation-bundle-2026-09-16-rebuild.tar`
- SHA256: `da0c37bedf20b61cb19512eefebcf01a709c0a68951445695f58e0d196c56700`

These private ignored artifacts contain only seven regular files:
`collector_launcher.py`, `inspect_binding.py`, `installation.py`,
`helper_entry.py`, `install.py`, `README.md` and `bundle.json`. `install.py` is
exactly the reviewed `infra/egress-guard/package.py` source. USTAR ordering,
metadata and padding are deterministic; the inventory hashes all six other files.
The format contains no credentials, journals, local database or upstream source.

The inspector requires the selected SHA256, bounds the archive to 8 MiB and each
member to 1 MiB, accepts only the fixed regular-member sequence and checks exact
canonical reserialization. Links, paths, duplicate/extra members, altered metadata,
trailing content and inventory drift are refused without extraction or execution.
A SHA256 pin establishes equality with reviewed bytes; it is not a publisher signature.

## Installation behavior prepared for review

The explicit `apply` command is implemented and unit-tested, **not run on this
host**. An operator must review the bundle and stage its exact installer in a
root-owned protected directory as a regular single-link 0444 file before running
it with `/usr/bin/python3 -I`. Both real/effective UID must be 0; the installer's
protected path and bytes must match the selected bundle. The checkout is not a
privileged entrypoint. Python, its standard library and the privileged operator
remain trusted; hostile root replacement races are outside this acceptance.

The exact mutations are limited to the fixed code directory, manifest, storage,
missing parent directories and dedicated account/group if absent:

| Object | Fixed destination / behavior |
|---|---|
| Code | `/usr/local/lib/trader-egress`, four root-owned 0444 sources; final directory 0755 |
| Manifest | `/etc/trader/egress-install.json`, root-owned 0600, v2, actual observed UID/GID and source hashes |
| Storage | `/var/lib/trader/egress`, root-owned 0700; preserve existing correct directory and all records |
| Account | `trader-egress`, system user and own primary group, `/nonexistent`, `/usr/sbin/nologin`, locked password, no supplementary groups |

Preflight checks root-owned ancestors without group/other write or symlinks, any
existing code/manifest, storage mode and account conflicts. A correct existing
account can be reused. A missing account is created with fixed `useradd` arguments
only when both its user/group are absent; no home, mail spool or login log entry is
created. `passwd -S` checks the `L` status before publication without exposing password hashes
to the installer. No fixed numeric ID is guessed. System account database
changes remain subject to the host's normal useradd implementation and policy.

Exclusive code-directory creation precedes account mutation and marks a partial
attempt. Sources and directories are fsynced, account policy is rechecked, the
manifest is published last and `TrustedInstallation` verifies the result. Failure
retains partial state for manual inspection; subsequent attempts refuse the code
root/manifest. There is no overwrite, upgrade, removal, rollback or consumed-scope
reset operation. A failure before the marker can leave only newly created parents.
Process/fsync tests do not qualify power-loss durability or storage rollback resistance.

The sole fixed public entry is
`/usr/bin/python3 -I /usr/local/lib/trader-egress/helper_entry.py --check`.
It establishes protected filesystem authority before loading the verifier, then
checks the complete v2 installation. Checkout calls and nonisolated Python are
refused. Valid installation reports `installation_verified_inactive`; failures
report blocked. Both return 2, with network/deployment admission and collector
started flags false. The new v2 manifest binds the entry itself as the fourth
source. v1 manifests are rejected; this installer cannot migrate an old installation.
No sudoers rule, daemon, network policy or activation operation is included.

## Verification

**321 focused Python tests pass**, adding 61 package/entrypoint cases and one
legacy-manifest refusal. Tests exercise actual private-directory writes and
no-follow descriptors with simulated account commands and substituted ownership.
They cover archive rejection, exclusive output, installer self-trust, entry trust,
unsafe account/storage refusal, manifest-last publication, preservation of consumed
bytes, failure descriptor cleanup, partial-state retention and no-retry behavior.
They do not perform actual useradd/password checks or establish cross-user isolation.

Actual `/usr/bin/python3 -I` build, rebuild and pinned inspect all pass. Checkout
entry invocation returns the expected refusal with exit 2. Ruff/check/format,
documentation links, contract source hashes and frozen prior artifact checks pass.
The unchanged 14-check rootless launcher and 151-check network harness were not
rerun; their previous results remain limited to disposable namespace fixtures.

```bash
.venv/bin/pytest -q tests/ops/test_egress_package.py tests/ops/test_egress_installation.py tests/ops/test_egress_collector_launcher.py tests/ops/test_egress_binding_inspection.py tests/ops/test_egress_host_inspection.py tests/ops/test_egress_guard_selftest.py
/usr/bin/python3 -I infra/egress-guard/package.py inspect --bundle data/egress-installation-bundle-2026-09-16.tar --sha256 da0c37bedf20b61cb19512eefebcf01a709c0a68951445695f58e0d196c56700
```

## Next implementation boundary

Review this exact inactive package for actual installation and dedicated-user
filesystem/process acceptance on an authorized host or correctly mapped disposable
environment. The current environment still lacks subordinate ID mappings/helpers;
no packages or mappings were installed to bypass this. Then qualify actual public
source mapping, complete egress paths, fixed storage/restart behavior and implement
the separate bootstrap transport and fixed activation operation.

The selected IPv4 and existing proxy remain unchanged. No maintenance interruption
was accepted or deployed. Frozen joint capture remains 17 GET / 468 weight; consumed
ADR-017/public-depth scopes are unchanged. Strict continuity remains **0/14**.
No upstream source or live trading path changed. `docs/project-status.md` and the
reading index now point to this concrete package milestone.
