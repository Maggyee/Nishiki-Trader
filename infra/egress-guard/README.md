# Isolated egress hook acceptance

Purpose: exercise OUTPUT/FORWARD hooks, expiring permissions and observed-loss
refusal in disposable Linux namespaces.
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

The namespace topology models hook behavior. It does not reproduce Docker NAT,
the full Tailscale rules, UDP/QUIC, cloud source mapping, an actual proxy, DNS
rotation, offload or provider-wide quota scopes. No production identity
authorization, persistent guard lease or complete traffic-loss detector is
implemented. Rule-removal tests demonstrate restored fixture connectivity;
deployment still requires stopping collection before removing its guard.

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

Next implementation entrypoint: bind an actual source/identity to this controller
boundary, with authenticated caller admission, persistent audit/restart handling
and a separately resolved first-request bootstrap contract.
See the
[VPS assessment](../../docs/progress/portfolio-vps-egress-assessment-2026-09-15.md).
The frozen first-request/bootstrap blocker remains independent of sudo access.
