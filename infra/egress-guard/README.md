# Isolated egress hook acceptance

Purpose: exercise OUTPUT/FORWARD hooks, expiring permissions, observed-loss
refusal and fixed-scope journal persistence in disposable Linux namespaces and
offline disk tests, and retain read-only host deployment-input snapshots.
Current phase: Phase 5 entry, offline infrastructure acceptance only. This is not
a production guard, gateway audit service, quota authority or collection permit.

Run from the project root as an ordinary user, without sudo:

```bash
/usr/bin/python3 -I infra/egress-guard/selftest.py
```

The standalone stdlib script supports system Python 3.10+. It creates a new user,
network, mount and PID namespace, verifies their identities differ from the
caller, and requires initially empty links/routes/rules (except loopback). It then
creates a router, bridge client and dual-stack echo peer with fixture-only routes.
There are no physical interfaces or external/default routes in the fixture.
All nftables, veth and forwarding-sysctl changes occur after the isolation check.
Audit exercises use a 1 MiB tmpfs mounted at `/tmp` only inside the private mount
namespace. These files disappear with the fixture; the host `/tmp` is unchanged.
No named namespaces, host files, packages or long-running services are installed.
The script rejects arguments and host-root execution; child commands use absolute
paths, isolated Python and a fixed environment. The worker has a 90-second alarm
and its parent a 100-second timeout. Exiting the disposable PID namespace kills
its children and releases the temporary network resources.
After creating each child network namespace, `setpriv` drops all effective,
permitted, inheritable, ambient and bounding capabilities and sets no-new-privs
before starting its client/server interpreter. Only the trusted fixture worker
retains namespace administration capabilities. Kernel tests verify the sender
cannot change its route or enter the worker's network namespace.

Acceptance covers IPv4/IPv6 host OUTPUT and bridge FORWARD, rejection after an
earlier independent accept, fresh and already-connected TCP traffic, unaffected
control destinations, fixture source spoof rejection, and removal of only the
owned guard table while preserving the earlier policy. Failed probes must also
increment the intended nft counter. Packet counts are not API request counts.

## Expiring permission and local dispatch supervision

The additional IPv4-only fixture permits one bridge source/destination/port through
an nftables timeout set. Its FORWARD chain defaults to drop and never exempts
established outbound traffic. Absent/revoked/expired elements block requests,
including existing TCP sockets. Host callers, a spoofed source and IPv6 fallback
are rejected in the fixture. Return traffic has a separate fixed rule; expiry
blocks outgoing requests, not every already-in-flight response.

`FixtureDispatchGuard` owns a serialized test-client invocation and at most four
attempts per instance. It compares the selected namespace, client route and guard
structure before preparation, after fsync and after the transport call. Dynamic
packet counts and remaining element lifetime are excluded from structural equality;
expiry enforcement belongs to the kernel. The journal uses exclusive creation,
original-file identity and exact-prefix checks. Prepared events precede sending;
failed/uncertain sends retain consumption. Missing/rewritten/replaced audit bytes,
write/fsync errors, changed observations and transport failures permanently halt
that object. Restoring configuration does not clear its halt; reopening the same
archive is refused. A different archive is still possible: this is not a global
one-shot scope, restart authority or quota reservation implementation.

There is deliberately no claim that snapshots close the check-to-send race.
The actual fixture deletes the table after the last check and demonstrates one
successful local send before the post-send check halts the supervisor. That attempt
remains prepared/uncertain. Report field `uncontrolled_rule_mutation_race_closed`
stays false. A production controller and a transport-bound
policy are still needed; arbitrary privileged changes can defeat
the observed boundary. Tmpfs fsync and abrupt-process tests do not prove survival
of host power loss. There is no gateway evidence adapter or persistent service.

## Controlled terminal revocation

`ControlledFixtureGuard` adds a terminal shutdown operation using the same lock as
dispatch. A stop event is set before waiting for that lock, so queued sends cannot
overtake the stop; an already-running request may finish first. The worker then
records `stop_requested`, empties the kernel permission set, verifies the empty
set and records `revoked`. It preserves the default-deny table. There is no
in-place policy replacement, renewal API or reactivation of the stopped object.

Dispatch failure also attempts revocation under the lock. Audit failure cannot
skip that attempt; failed revocation is not reported as successful and is not
automatically retried. The existing TTL remains the fallback. Close drains through
shutdown, closes the journal and is idempotent. A guard binds its creating PID
and refuses inherited-process dispatch/shutdown before locking, preventing use
of a fork-inherited lock or journal. This is process ownership, not authentication
of a public IPC API.

Actual tests pause a local send while concurrent shutdown and another send queue:
only the first request executes, then permissions are revoked. A separate
controller process crashes after preparation; its original event remains and
the kernel blocks the raw sender after the two-second test TTL expires. Death
does not imply immediate revocation. Capability dropping does not by itself
force every possible client in that namespace to journal requests. The fixture
assumes its fixed client command channel and worker are trusted; it grants no
complete all-caller quota or production isolation claim.

The initial namespace topology models hook behavior. The shared-source extension
below adds explicit local SNAT, UDP echo and a TCP tunnel proxy. It does not
reproduce full Docker/Tailscale or sing-box behavior, QUIC, cloud source mapping,
DNS rotation, offload or provider-wide quota scopes. No production identity
authorization, persistent guard lease or complete traffic-loss detector is
implemented. Rule-removal tests demonstrate restored fixture connectivity;
deployment still requires stopping collection before removing its guard.

## Persistent fixture scope and read-only crash replay

`PersistentFixtureGuard` extends the same controller with one fixed
`fixture-scope-v1/attempts.jsonl` beneath a pre-existing, caller-selected private
storage root (owned by the process user, mode 0700). Exclusive directory creation
claims the scope before any transport call. The root directory is fsynced, then
the new journal's directory entry and activation record are fsynced. Every
preparation retains the existing write/fsync-before-send rule. Failed startup
leaves the scope consumed; another process cannot choose a different journal name
within that root to bypass the marker. Existing scopes are always refused, even
if empty or terminal. There is no resume, reset or lease-grant API.

Directory identity/permissions and journal links/permissions are checked alongside
the existing byte-prefix checks. Observed storage loss halts dispatch and attempts
kernel revocation. This assumes a trusted, stable storage root and filesystem;
changing roots, deleting markers, restoring backups or privileged concurrent
filesystem mutations are not prevented by this fixture.

`review_fixture_journal` replays explicitly hash-selected bytes and source identity,
validates canonical records, hash links, clocks and lifecycle transitions, and
reports recorded preparations and any pending uncertain attempt. Revocation does
not erase an uncertain send. Its restart/admission/coverage flags are always false.
Malformed or incomplete records fail review; a valid incomplete lifecycle is
reviewable but cannot resume. An observed-now hash is not historical provenance,
and a caller-rehashed valid prefix cannot prove absence of missing later records.

The Linux harness adds four actual controller checks using its private tmpfs.
The focused Python suite separately exercises ext4-backed process crashes at five
stages, two fresh replays of each available journal, concurrent ownership, startup
fsync failures, storage loss and tampering. Run it with
`uv run pytest -q tests/ops/test_egress_guard_selftest.py`.
These tests establish process-exit persistence and the requested OS fsync ordering;
they do not simulate host power loss, filesystem rollback or restart admission.
Controller death still relies on the kernel lease TTL. No host guard or real
collector uses this backend. Detailed evidence and boundaries are in the
[persistent-scope report](../../docs/progress/portfolio-vps-egress-persistence-2026-09-16.md).

## Optional host read-only sudo

The agent currently runs as `orca`. Namespace acceptance needs no host sudo.
To let it independently read the active host rules, the operator can run:

```bash
sudo visudo -f /etc/sudoers.d/orca-trader-audit
```

Enter exactly:

```sudoers
orca ALL=(root) NOPASSWD: /usr/sbin/nft -j list ruleset
```

Then validate with `sudo visudo -c`. The agent can call
`sudo -n /usr/sbin/nft -j list ruleset`. This grants only that read command, not
general nft, shell, Python, package, Docker or root access. No password should be
sent in chat. Revoke this entry using `sudo rm /etc/sudoers.d/orca-trader-audit`
and recheck `sudo visudo -c`. No sudoers file is installed by the repository script.

## Read-only shared-source preparation

The operator now selects the existing public IPv4, superseding the earlier
dedicated-address proposal. The [shared-source revision](../../docs/progress/portfolio-shared-egress-bootstrap-2026-09-16.md)
specifies caller coverage and prospective bootstrap requirements. No new address
is needed. No host guard is deployed.

```bash
/usr/bin/python3 -I infra/egress-guard/inspect_host.py \
  --nft-via-sudo --storage-root /var/lib/trader/egress \
  --report data/NEW-EGRESS-HOST-SNAPSHOT.json
```

Seven fixed local read commands capture link/address, route/rule and nft state.
The sudo option uses only the read grant above; without it nft runs as the current
user. Storage inspection reads metadata only. Missing permissions/tools, malformed
output and timeouts remain explicit. The exclusive 0600 report contains raw host
details; stdout contains only counts, blockers and a hash. Use a trusted output
parent and keep the report private/ignored. Exit 2 means written but unqualified;
exit 1 means report failure. This is a non-atomic snapshot, not a cloud mapping,
historical ledger, deployment authority or network permit. No DNS, venue, cloud
metadata, credentials or proxy configuration are accessed.

## Shared-source NAT and proxy acceptance

The same `selftest.py` now includes 49 additional actual kernel checks: direct
host, collector, competing routed caller and two proxy-client paths are observed
at the peer with one SNAT source. Selected destinations are blocked for new and
existing TCP sockets and UDP/IPv6 alternatives; other-address direct/proxy controls
remain usable. The proxy is an unprivileged bounded fixture tunnel, not sing-box.
The persistent controller prepares before the actual collector send, and terminal
revocation blocks its existing connection. Rollback follows collector closure and
preserves the earlier independent policy. All mutations remain inside disposable
namespaces; no host sudo or real venue is involved.

Two negative results are intentional: an unlisted destination remains reachable
with the shared source, and a separate service on the protected IP is also blocked.
Therefore the report retains false provider-wide coverage and cohosted-service
preservation flags. See the [acceptance report](../../docs/progress/portfolio-shared-egress-acceptance-2026-09-16.md).

Next establish the real provider/caller coverage policy and proxy effects, or
prepare a bounded maintenance-window alternative with watchdog/rollback for review.
Do not deploy a three-hostname IP list as exhaustive coverage or silently stop
existing services. Actual source/caller/fixed-storage binding and the separate
one-GET REST bootstrap implementation/review remain necessary. No proposal or
consumed scope is activated by these fixture results.

## Bounded maintenance alternative

The same isolated harness now includes `FixtureMaintenanceWindow` and 46 additional
Linux checks. Its default 12-second collector permission expires before the
20-second other-caller blackout. Both are installed atomically; terminal shutdown
flushes both atomically. The collector's permanent deny remains after ordinary
traffic resumes. A process-owned lock serializes activation/revocation; failed
activation cannot retry, and missing sets cannot masquerade as verified release.

Actual abrupt-exit and SIGSTOP/SIGCONT scenarios exercise shorter 1/4-second
deadlines. Kernel expiration restores ordinary direct/proxy requests while keeping
the collector blocked, even without an active controller. The resumed owner halts;
the persistent request journal retains its uncertain send. No userspace watchdog
process is required for this fixture fallback. The overall worker still has its
90-second bound and the parent its 100-second bound.

This broad window intentionally interrupts unrelated WAN egress, including existing
connections, IPv6 and UDP. It is a candidate for a separately accepted interruption,
not a way to promise uninterrupted proxy access. Actual complete paths,
source/fixed-storage binding and a privileged helper remain implementation work. No
host policy or real one-shot bootstrap is installed. See the historical
[maintenance proposal and acceptance](../../docs/progress/portfolio-maintenance-window-2026-09-16.md).

`PersistentFixtureMaintenanceWindow` now wraps the kernel controller with a separate
fixed `fixture-window-v1/attempts.jsonl`. Exclusive scope creation, directory fsyncs
and a fsynced `prepared` record precede any kernel activation. The activation
journal permits only one preparation; initialization failure, uncertain kernel
results and terminal shutdown never allow reopening or renewal. Identity binds
the timer settings, literal fixture rules hash and selected namespace/route/rules
snapshot. Only the two owned timer memberships are omitted from the window's
structural binding; the request journal still observes active membership.

The journal's `activated` record means a storage claim, not a kernel permission.
`succeeded` records the kernel command returning and a matching observation, not
complete traffic coverage. A pending preparation remains uncertain after cleanup.
Close before activation performs no kernel operation; its cleanup record is a
terminal no-op. Journal failure cannot bypass cleanup after an attempted activation.
`review_window_activation` only replays selected bytes and always denies restart,
capture admission and gateway qualification.

Actual namespace acceptance includes abrupt exit after the kernel command but
before its return record or any request journal. Kernel expiry still restores
ordinary traffic and keeps the collector quarantined. Separate disk tests crash
at six lifecycle stages, reproduce two fresh-process replays and refuse fresh
initializers without changing original bytes or calling the kernel. The trusted
caller-selected root remains a boundary: changing/deleting it or restoring old
storage is not prevented, and process crashes/fsync order do not prove host
power-loss durability. See the [persistent-window report](../../docs/progress/portfolio-maintenance-persistence-2026-09-16.md).
