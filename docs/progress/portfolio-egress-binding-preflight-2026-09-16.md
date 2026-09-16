# Read-only host binding and drift preflight

The existing-public-IPv4 work now has a read-only preflight that binds selected
local network state, host/process identities and fixed storage metadata, and
compares them with pinned previous bytes. It follows the
[durable window activation acceptance](portfolio-maintenance-persistence-2026-09-16.md).
This prepares the inputs for a future privileged helper; it does not implement
that helper, authorize a caller or install a host guard.

## Implemented checks

`infra/egress-guard/inspect_binding.py` reuses the existing inspector's seven fixed
local read commands. It selects the WAN interface and assigned local IPv4 explicitly,
requires that interface's observed IPv4 default route, and retains all observed
links, addresses, IPv4/IPv6 routes and policy rules, and nft rules. An interface
default route is a necessary local consistency check, not proof that policy
routing actually sends a particular request there or covers every external path.

The binding also records the host boot ID and network/user/mount namespaces.
Optional collector PID inspection records start ticks, four UID/GID values,
groups, five capability sets, no-new-privileges, namespaces, cgroup hash and
executable device/inode/size/mtime. Process lifetime is checked during the metadata
read, and host/process metadata must agree across the network snapshot. A missing
process, root or mixed UIDs, any retained capability, absent no-new-privileges or
the host's network namespace prevents local completeness. Arguments, environment,
credential files and process memory are never read. Metadata is not executable
content attestation, dedicated-UID authorization or ownership of a live pidfd.

The future host authority's storage path is fixed to `/var/lib/trader/egress`.
Every observed component must be a root-owned directory without group/other write
permission; the final directory must be mode 0700. Symlink components, missing
metadata, another root, unsafe ancestors and a public final directory fail. No
directory, journal or consumed marker is created. The fixture remains unchanged
and uses its separate caller-owned test root; it has not been promoted into a
root service. ACLs, mounts, filesystem behavior and rollback protection still
require qualification by the actual storage owner/helper.

Pinned comparison requires both an original report path and its SHA256, validates
the profile and internal binding hash, and reports changed binding sections. Only
known observational nft counter values and route/address lifetime fields are
excluded from equality. Quota limits, policy selectors, namespace identity,
interface indices, executable metadata and storage device/inodes stay bound.
Equal incomplete snapshots always report `local_binding_matches=false`.

Reports are exclusive mode-0600 files, capped at 32 MiB; existing files and symlinks
are not replaced. Prior input reads reject symlinks/nonregular files without
blocking on FIFOs. Invalid selected bytes fail before any local commands. stdout
contains only status, blockers, report hash and comparison field names. Raw host
details remain local. Exit 2 means a review report was written, including for a
matching complete local observation; there is no admission-success exit code.

## Actual host observation

Two actual read-only runs on September 16 used the existing `enp0s6` interface and
the single local IPv4 selected from the retained earlier host snapshot. Neither
run selected an arbitrary existing process as the collector. Both completed all
seven allowlisted network reads, using only the previously documented read-only
nft sudo command. They observed:

- 27 interfaces, two IPv4 default-route entries and one IPv6 default-route entry;
- seven IPv4 and six IPv6 policy rules, including the existing tunnel policy;
- 27 nft base chains and no nft flowtable in this snapshot;
- no selected collector and missing/unreadable fixed storage.

The second run pins the first report's original hash. It finds no structural drift
but correctly refuses a complete local binding. Zero observed nft flowtables does
not prove absence of tc/eBPF, hardware offload, other namespaces or tunnel bypass.
Both reports keep public-source, caller, storage, host-deployment and network
qualification false, with zero venue requests.

Private local artifacts (not committed):

| Report | SHA256 |
|---|---|
| `data/egress-binding-inspection-2026-09-16.json` | `d8bb9b5bac465a7893db7d6ddebe023d39a9909326c017e37cfc1f88362879ad` |
| `data/egress-binding-inspection-2026-09-16-compare.json` | `741d35b8344bbd552ab27bc40ab7fe76dbb78690a043610c99148752881b37a6` |

These hashes identify observed local bytes, not an independently authenticated
cloud mapping or historical enforcement record. Repeated equal observations do
not make the sequence atomic, prevent a change-and-restore race or establish future
enforcement. Reading host state did not alter firewall rules, routing, proxy
settings, services or kernel window membership.

## Verification and next implementation

**186 focused Python tests pass**, including 37 new binding cases. Coverage includes
host restart, namespace replacement, PID reuse, executable/storage inode changes,
IPv4/IPv6 and policy-route changes, source reassignment, quota drift, safe handling
of counters/lifetimes, unsafe storage ancestors, process privilege failures,
incomplete reads, malformed pinned inputs and private output/no-overwrite behavior.
The actual current Python process also exercises the `/proc` metadata reader.

```bash
uv run pytest -q tests/ops/test_egress_binding_inspection.py tests/ops/test_egress_host_inspection.py tests/ops/test_egress_guard_selftest.py
uv run ruff check infra/egress-guard/inspect_binding.py tests/ops/test_egress_binding_inspection.py
uv run ruff format --check infra/egress-guard/inspect_binding.py tests/ops/test_egress_binding_inspection.py
```

Ruff/format, local links, frozen proposal/contract bytes and diff checks pass.
The unchanged 151-check Linux harness and full application regression were not
rerun for this separate read-only utility.

Next implement a reviewed collector launcher and authenticated helper boundary:
the helper must own the fixed storage and trusted installed code, derive caller
identity from its own process/IPC handles, and refuse arbitrary commands, rules,
paths, retries or renewal. A supplied PID or matching report is never that
authority. Then bind the current VNIC/public mapping, verify complete real
host/container/tunnel/proxy paths, and qualify startup failure/restart/rollback
before preparing host rollout. Read-only preflight is usable now; real source and
caller authorization remain incomplete.

The 20-second maintenance interruption is still unapproved and undeployed. The
separate one-GET bootstrap remains Draft/unimplemented, the frozen 17-GET /
468-weight joint contract is unchanged, and consumed ADR-017/public-depth scopes
remain consumed. Strict continuity is **0/14** and live trading is blocked. No
upstream source, trading execution path, credential or real venue was touched.
