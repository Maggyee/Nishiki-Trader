# Isolated gateway consumes the prospective attempt ledger

Date: 2026-09-17. Disposable Linux namespaces and local echo peers only.

The [local attempt ledger](portfolio-egress-attempt-ledger-2026-09-17.md) now has
an actual kernel-backed fixture consumer in `infra/egress-guard/ledger_gateway.py`.
The prior guard opened forwarding permission to a client namespace, where another
client socket could bypass the ledger while permission remained active. This
fixture instead keeps the outgoing socket in the trusted gateway, leaves forwarding
denied, and requires durable preparation before installing a short-lived socket
mark permission. It sends a fixed echo as the fixture representation of one
exchangeInfo operation; it does not implement HTTP/TLS, real API collection or quota
admission. There were zero venue requests or host network/service changes.

## Implemented boundary

The public script accepts no arguments, refuses host-root execution, and runs with
system Python 3.10 in fresh user/network/mount/PID namespaces. It reuses the existing
empty-topology isolation check before any mutation, then connects only reserved
local fixture networks. No external/default route, physical device or public
endpoint is added. A private 2 MiB tmpfs holds disposable archives. The worker has
a 40-second alarm and the parent a 45-second deadline with process-group cleanup.
Exact source bytes for the ledger and two stdlib dependencies are embedded into
the isolated interpreter; no repository/site import search path is enabled.

The existing `FixtureCollector` launches a capability-dropped child with
no-new-privileges in an unconnected network namespace. Private SOCK_SEQPACKET
messages are authenticated using per-message kernel PID/UID/GID credentials;
pidfd and selected process metadata are checked independently. The child's finite
`observe`/`observed` handshake confirms its identity before preparation. It does
not supply a destination, payload, caller label, cost or command. This is one
trusted fixture collector, not a newly implemented multi-client broker protocol.

`FixtureLedgerGateway` is bound to its creating PID and shares a lock between
fixed dispatch and terminal revocation. It consumes its single invocation before
authentication. The real `AttemptLedger` then fsyncs a preparation, checks its
borrowed binding, and performs another checkpoint before grant. The fixture
binding includes the authenticated child's metadata, namespace, selected route
and structural nft rules. Set contents are deliberately excluded from this
structural fingerprint because the controller changes them; the kernel enforces
their lifetime, and revocation separately verifies the empty set.

The gateway installs a five-second `meta mark` permission only after durable
preparation, checks the ledger/binding again and calls the fixed sender. The
sender creates its own marked TCP socket to `198.51.100.2:23456`, sends a fixed
13-byte echo, checks the echo and closes the socket. No descriptor is handed to
the child. OUTPUT accepts only the mark plus that destination/port; all other
OUTPUT and all FORWARD traffic are dropped, including IPv6. A capability-dropped
process in the gateway namespace cannot set SO_MARK. This models an exclusive
fixture egress path, not selective preservation of a running production proxy.

Success records the outcome before terminal revocation. Any failure also attempts
revocation, including authentication, persistence or transport failure. Revocation
flushes and checks the permit set while preserving the deny table; failure cannot
be reported as successful or automatically retried. A stop flag is set before
waiting for the dispatch lock. Stop observed before grant or send prevents the
send; an invocation already inside its transport step may complete before the
revoker obtains the lock. Queued invocations are refused. There is no renewal,
retry, resume or public destination override.

The attempt ledger remains unchanged. A preparation followed by cancellation or
unrecordable outcome stays uncertain. The gateway's grant/revocation state is
in-memory and returned in the fixture report, not an independently durable kernel
lease journal. A crash does not imply a recorded revocation; this new integration
does not test controller death or power-loss. The five-second nft timeout is a
configured fallback, not an instant-death guarantee. The earlier ledger crash
acceptance is retained separately.

## Verification

**22 new / 303 focused Python tests pass; 21 actual Linux fixture checks pass.**
The kernel run covers host/forwarded baseline connectivity, unrecorded host and
forwarded denial, IPv6 fallback denial, denial while the gateway permit is active,
SO_MARK forgery refusal, a persisted local echo, managed concurrent stop/queued
refusal, stop after preparation, rule drift before and after grant, failed
preparation fsync, verified revocation and consumed-scope reopen refusal.

Six independent private fixture roots retain the following outcomes:

| Scenario | Confirmed local echoes | Persisted preparations | Historical outcome |
|---|---:|---:|---|
| success | 1 | 1 | succeeded, then closed |
| concurrent_stop | 1 | 1 | succeeded; queued invocation refused |
| stop_after_prepare | 0 | 1 | uncertain, closed |
| rule_drift | 0 | 1 | uncertain, explicit gap |
| rule_drift_after_grant | 0 | 1 | uncertain, explicit gap |
| fsync_failure | 0 | 0 | incomplete prefix, no resume |

No failed scenario refunds or reopens its original scope. The fsync failure
occurs before a preparation is acknowledged and before grant; the consumed
creation marker remains even though the journal retains zero preparations.
Each of the six exact archives is exported from the isolated worker's result,
then replayed by **two new CLI processes**. All twelve return 2 and each pair is
byte-identical to the worker's replay. Original archives, selected bindings,
reports and source hashes are pinned in the [result JSON](portfolio-egress-ledger-gateway-2026-09-17.json).
Local artifacts are under `data/egress-ledger-gateway-2026-09-17/`.

Focused regression covers the new gateway, attempt ledger, prior isolated guard,
collector credential/IPC validation, authority binding and TLS journal suites.
It includes wrong PID/UID/GID, same-UID foreign sender and ancillary descriptor
refusal in the reused control channel. New unit cases additionally verify
preparation before grant, transport/audit failures, revocation failure, concurrent
stop ordering, fork ownership, repeated close and parent timeout cleanup.
Initial fixture setup omitted an IPv6 alias required by the reused echo peer;
a later fault-injection callback was not wired into its intended scenario. Both
acceptance-harness defects were fixed before the retained passing run.
Ruff/format, links, evidence pins and diff checks pass. The full application suite
and the unchanged older kernel scripts were not rerun.

## Remaining work

The trusted gateway and namespace administrator can create marked sockets or
change rules. Arbitrary privileged rule deletion is not serialized by this
controller, and the old observed check-to-send race is not claimed closed.
Rootless helper/child share a mapped UID; dedicated host UID, filesystem separation,
installed source custody and fixed global storage still need an integrated profile.
Selected fixture process credentials are not real host/container/Tailscale/proxy
caller authorization. The underlying ledger reports continue to deny complete
coverage, known usage upper bounds, future enforcement, network and trading
admission. Echo counts and nominal weight 20 are not real provider usage.

Next join this socket ownership model to fixed installation/dedicated-UID authority
and durable kernel activation/revocation records in a disposable acceptance profile;
exercise controller crash and expiry there before proposing any real deployment.
Fresh provider clocks/rates, unresolved charges and complete historical/future
shared-IP bounds remain blockers. No new maintenance window or bootstrap retry is
authorized by this fixture. The real bootstrap is still consumed; the frozen joint
contract remains 17 GETs / 468 documented weight, strict continuity 0/14, live
trading blocked. Upstream code and the live order path are untouched; project
status, reading index and the infrastructure README are updated.
