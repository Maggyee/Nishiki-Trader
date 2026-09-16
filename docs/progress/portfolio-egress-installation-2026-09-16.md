# Fixed installation authority and nonroot launch implementation

The existing-IPv4 work now implements fixed installation checks and an explicit
nonroot collector-launch branch. This follows the
[isolated launcher acceptance](portfolio-collector-launcher-2026-09-16.md).
The [machine-readable installation contract](portfolio-egress-installation-contract-2026-09-16.json)
pins fixed paths, modes and source hashes. No account, package, privileged command
grant, host guard or service has been installed.

## Authority checks implemented

`TrustedInstallation` in `infra/egress-guard/installation.py` opens only these fixed
locations:

| Object | Location and required ownership/mode |
|---|---|
| Installed code | `/usr/local/lib/trader-egress/{collector_launcher,inspect_binding,installation}.py`, root-owned regular single-link files, mode 0444 |
| Installed manifest | `/etc/trader/egress-install.json`, root-owned regular single-link file, mode 0600 |
| Helper storage | `/var/lib/trader/egress`, root-owned directory, mode 0700 |

Every ancestor directory must be root-owned and have no group/other write bit.
Paths are traversed with retained directory descriptors and `O_NOFOLLOW`; files
are opened nonblocking to reject FIFOs without hanging. Each file is bounded to
1 MiB. Symlinks, hardlinks, wrong owners/modes, missing files and unknown source
names fail before source loading. Descriptors are close-on-exec and are not
inherited by the collector.

The manifest has exactly the `portfolio.egress_installation.v1` schema selector,
`collector` identity and `files` hash map. Collector identity must equal the
currently observed dedicated account name and numeric UID/GID. The files map must
contain exactly the three fixed source basenames and their SHA256 strings. The
linked review contract has a different schema and is not a copy-ready installed
manifest; its numeric account IDs remain null until actual provisioning.

Account policy requires `trader-egress`, nonzero UID/GID, its same-named primary
group, `/nonexistent` home and `/usr/sbin/nologin` shell. Other passwd entries cannot
share its UID or primary GID. Group aliases, extra group membership and unrelated
members in its primary group are rejected. Password locking remains a provisioning
requirement; no shadow or credential file is read by this checker.

Revalidation compares account policy, mount namespace, original path/device/inode,
ownership/modes and exact original bytes. An observed change closes all retained
descriptors and permanently invalidates the object. Restoring an old path does not
reactivate it. Directory link counts are not bound, allowing the helper to create
its own consumed-scope subdirectories; file single-link checks remain mandatory.

This is authority checking under an already trusted startup, not bootstrap trust
in an arbitrary script invocation. A future privileged entrypoint must itself run
root-owned installed code, never execute the checkout as root or accept a supplied
installation object/path. Privileged replacement races, storage rollback, host
power loss and complete interpreter/system-library integrity remain outside this
acceptance.

## Launcher connection

The internal `FixtureCollector.from_installation` entry loads only the verified
reader and launcher bytes, selects the pinned account IDs and adds the manifest
hash to the process identity. Every process identity check also revalidates the
held installation authority. Closing or invalidating that authority prevents its
continued use.

The new dedicated branch explicitly uses `setpriv --reuid=UID --regid=GID
--clear-groups`, alongside capability removal and no-new-privileges. The helper
expects the selected UID/GID in kernel message credentials and requires all four
observed UID/GID values to match, with no supplementary groups. Zero, boolean,
incomplete or same-as-helper UID selections are refused before spawning. This is
an internal integration branch, not a new root CLI, daemon or network permission.

## Verification and current host result

**259 focused Python tests pass**, adding 32 installation and 11 launcher cases.
Tests cover no-follow descriptor traversal, symlinks, hardlinks, FIFOs, unsafe
ancestors, source tampering, path replacement, identity/group changes, failure
descriptor cleanup, private reports and permanent invalidation. Unit filesystem
tests substitute a private test root and its owner; the public CLI has no such
override. Launch tests verify requested ID/group reduction, observed-identity
refusal and installed-source/manifest binding with mocked process creation.

The updated launcher also passes all **14 actual isolated integration checks**
again, including kernel credentials, pidfd death, helper crash, durable kernel
window/IPC ordering and cleanup. These retain the original same-UID rootless map;
they do not exercise the newly implemented distinct-UID branch.

Read-only local inspection found no subordinate UID/GID allocations for the
current user and no `newuidmap`/`newgidmap` executables. The installed `unshare`
supports only the available single-user mapping in this environment. No mappings,
packages, users or permissions were changed to bypass that limitation. Actual
cross-user storage/code protection and nonroot startup therefore remain unverified.

The actual installation checker returned exit 2 with
`installation_missing_unreadable_or_invalid`; it wrote the private ignored report
`data/egress-installation-check-2026-09-16.json`, SHA256
`9a24ae361c8d9aab0effca0f0421d619829ccdc04d30d67ed6029fb7fd7cdc5e`.
This reports current inability to qualify the fixed installation, not an installed
service or a deployment permit. No filesystem scope was consumed by inspection.

```bash
/usr/bin/python3 -I infra/egress-guard/installation.py --report data/NEW-INSTALLATION-CHECK.json
/usr/bin/python3 -I infra/egress-guard/collector_launcher.py
uv run pytest -q tests/ops/test_egress_installation.py tests/ops/test_egress_collector_launcher.py tests/ops/test_egress_binding_inspection.py tests/ops/test_egress_host_inspection.py tests/ops/test_egress_guard_selftest.py
uv run ruff check infra/egress-guard/installation.py infra/egress-guard/collector_launcher.py tests/ops/test_egress_installation.py tests/ops/test_egress_collector_launcher.py
uv run ruff format --check infra/egress-guard/installation.py infra/egress-guard/collector_launcher.py tests/ops/test_egress_installation.py tests/ops/test_egress_collector_launcher.py
```

Verified launcher SHA256 is
`d1d94a8edd0730244b6dbc7c0e24746157985e7b36b82f865397402ce0433579`;
installation checker SHA256 is
`04ceddded1d6b1df10c52285226c1ddf43a42d95129226d95cd4314675d902eb`.
The contract pins these and the unchanged binding inspector. Ruff/format, local
links, contract hashes, frozen prior artifacts and diff checks pass. The unchanged
151-check full network harness and full application regression were not rerun.

## Next step

Prepare a reviewable installation package and fixed privileged entrypoint using
this contract, then perform actual dedicated-user/filesystem acceptance under an
authorized host or an appropriately mapped disposable environment. Installation
must preserve consumed state and existing services. Complete public/private source
mapping, all external caller paths, storage restart/durability and rollout/rollback
remain necessary before the separately reviewed one-GET transport can be enabled.

The maintenance interruption remains unaccepted and undeployed. Existing proxy
traffic, the selected public IPv4, all frozen bootstrap/joint contracts and consumed
ADR-017/public-depth scopes are unchanged. Zero venue requests occurred; no upstream
source or live execution path changed. Strict continuity remains **0/14**, and live
trading remains blocked.
