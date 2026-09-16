# Isolated collector launcher and authenticated channel acceptance

The next existing-IPv4 increment implements a fixed child launcher and kernel-bound
control channel in a disposable Linux fixture. It follows the
[read-only binding preflight](portfolio-egress-binding-preflight-2026-09-16.md)
and reuses the existing durable maintenance-window and request journals. It is a
foreground selftest, not a deployed collector, root service or host sudo helper.

## Implemented boundary

`FixtureCollector` launches one fixed system-Python program through `unshare --net`
and `setpriv`, removes all five Linux capability sets and enables no-new-privileges.
Its environment and interpreter command are fixed, and only the child's private
Unix `SOCK_SEQPACKET` endpoint is explicitly inherited. No network transport,
credentials, arbitrary executable, destination or shell command is in its protocol.

The parent opens a pidfd for its actual spawned child and validates the readiness
message against kernel-provided per-message `SCM_CREDENTIALS` PID/UID/GID. A
socketpair's cached `SO_PEERCRED` refers to its creator before child execution;
the fixture verifies this directly and does not use it as child authentication.
UID equality alone is insufficient: another process with the same UID is rejected.

Each message must be canonical JSON with exactly version, operation and integer
sequence fields, within 1,024 bytes. Boolean sequence/version values, duplicates,
extra fields, stale sequences, unknown operations and truncated messages fail.
File-descriptor passing is forbidden; every delivered descriptor is closed before
rejecting ancillary data, including the prefix delivered with truncation. Both
directions use kernel credentials, and channel errors are terminal.

The finite protocol is readiness, at most one control observation, then close.
The helper independently reads the launched process's start ticks, UID/GID/groups,
capabilities, namespaces, cgroup and executable metadata. The selected identity
also contains the launcher-source SHA256. Pidfd liveness and process metadata are
checked before/after observation. The local attempt is consumed before sending,
and uncertain results never allow another send. A lock and process-owner checks
serialize observation/shutdown; cleanup closes descriptors and reaps the child.

On child death the original pidfd becomes readable, and the helper refuses another
observation. On abrupt helper exit its endpoint closes; the fixed child exits on
EOF or the bounded receive timeout. There is no reconnect, retry, renewal or
automatic replacement child. This identifies the launched process within the
fixture trust boundary; it is not a defense against privileged code injection or
a compromised trusted helper/collector.

## Integration with durable activation

The actual isolated sequence is:

1. Verify fresh user/network/mount/PID namespaces and empty links/routes/rules.
2. Launch and authenticate the capability-dropped child in another fresh network
   namespace. Its control socket/handshake exist before the dispatch journal;
   there is no IP connection or collection operation.
3. Install the literal fixture table and bind child/source identity plus observed
   rule structure. Persist the separate fixed window consumption/preparation, then
   activate its bounded kernel sets.
4. Persist a separate single control-observation preparation before sending it.
5. Revoke and verify the kernel window, close/reap the child, then replay both
   terminal journals. Existing request scopes cannot dispatch again.

The window is owned by the helper; the child has no activation or renewal command.
The activation and control journals retain different attempts and never grant
restart/admission authority. The existing network harness already exercises the
literal rules against local peers; this new fixture exercises launcher/controller
composition without connecting its child to an IP network. It does not collect an
HTTP response or qualify real traffic coverage.

## Verification

**14 isolated integration checks and 216 focused Python tests pass**, including
30 new launcher/channel cases. The integration runner covers authenticated
readiness, namespace/capability constraints, the cached-peer-credential distinction,
durable window/IPC ordering, separate journal replay, terminal teardown, consumed
scope refusal, pidfd exit and abrupt helper death. Focused tests use actual local
Unix sockets and a forked same-UID impostor, and cover protocol errors, timeout/EOF,
descriptor cleanup, duplicate requests, failures before/during/after IPC, inherited
owner refusal and cleanup after pidfd acquisition failure.

```bash
/usr/bin/python3 -I infra/egress-guard/collector_launcher.py
uv run pytest -q tests/ops/test_egress_collector_launcher.py tests/ops/test_egress_binding_inspection.py tests/ops/test_egress_host_inspection.py tests/ops/test_egress_guard_selftest.py
uv run ruff check infra/egress-guard/collector_launcher.py tests/ops/test_egress_collector_launcher.py
uv run ruff format --check infra/egress-guard/collector_launcher.py tests/ops/test_egress_collector_launcher.py
```

The public entrypoint refuses host-root execution and arguments. A 25-second
worker alarm and 30-second parent timeout bound the run; exiting the disposable
PID namespace terminates its remaining children. A private tmpfs holds journals;
no host path, named namespace, socket listener or service is installed. nft
mutations occur only after isolation checks and only in the disposable namespace.

Verified source hashes:

| Source | SHA256 |
|---|---|
| `infra/egress-guard/collector_launcher.py` | `225738575fe355b194bf41e24bb03228a05e2e4d15ae9930c5c1a141ad157a55` |
| reused `infra/egress-guard/selftest.py` | `75ba8a36ca075f4236f20e68524117bf1abc1431226271bb0df35912c4ebff5f` |
| reused `infra/egress-guard/inspect_binding.py` | `27c3302222bc819767ba874d7000f2b038662fa72004cb56da25a1003c38e322` |

Ruff/format, local links, immutable prior artifacts and diff checks pass. The
unchanged 151-check full network harness and full application regression were not
rerun; the new runner executes its own actual isolated kernel window operations.

## Remaining host requirements

This rootless fixture maps helper and child to the same namespace UID 0. The child
has no capabilities, but this does not supply a dedicated host UID or filesystem
separation: changed trusted child code could access same-UID fixture files. Do not
install this harness as a privileged helper or mistake its internal trusted-source
parameters for a public API. Production needs root-owned installed code/config,
a dedicated unprivileged collector identity, fixed storage owned by the helper and
an authenticated fixed-operation launch boundary. Observed executable metadata and
source hashes do not prove installed code authority or prevent storage rollback.

Next establish those installation/identity/storage constraints, bind the current
cloud public/private mapping and complete host/container/tunnel/proxy paths, then
integrate the separately reviewed one-GET transport. Host startup/restart failure,
durability, rollout/rollback and out-of-band recovery remain unqualified. The
20-second interruption still requires acceptance before deployment; this fixture
does not interrupt existing proxy traffic or change the current public IPv4.

All output admission/deployment flags remain false. Zero venue requests occurred;
no credentials, upstream source or live execution path changed. Existing bootstrap
proposals and the frozen 17-GET / 468-weight contract remain unchanged. Consumed
ADR-017/public-depth scopes stay consumed, strict continuity remains **0/14**, and
live trading stays blocked.
