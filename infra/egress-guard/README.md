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

## Read-only host binding preflight

`inspect_binding.py` adds local identity and drift checks around the same seven
allowlisted host reads. Select the existing WAN interface and its assigned local
IPv4 explicitly; a local address is not the cloud-mapped public IPv4. Example
(replace the uppercase placeholders with selected local values):

```bash
/usr/bin/python3 -I infra/egress-guard/inspect_binding.py \
  --wan-interface SELECTED_INTERFACE --source-ipv4 SELECTED_LOCAL_IPV4 \
  --nft-via-sudo --report data/NEW-BINDING-SNAPSHOT.json
```

Once a reviewed launcher exists, `--collector-pid PID` observes that process's
start ticks, UID/GID/groups, all five capability sets, no-new-privileges, network/
user/mount namespaces, cgroup hash and executable metadata. It does not launch,
signal or authorize the process, read its arguments/environment or access credentials.
The host boot/namespaces and collector metadata must agree before/after the local
snapshot. Missing process data, root/mixed UIDs, retained capabilities, missing
no-new-privileges or a shared host network namespace remain explicit blockers.

Storage is fixed to `/var/lib/trader/egress`; there is no alternate-root CLI option.
It requires observed root ownership and no group/other write permission on every
ancestor, with a final mode-0700 directory and no symlink component. Metadata checks
create no directories or consumed markers and grant no storage authority. This
future helper requirement differs from the fixture's caller-owned temporary root.
The embedded legacy inspector retains its own reader-ownership status; the new
preflight derives the stricter root requirement from the component observations.

Add `--compare data/PRIOR.json --compare-sha256 PRIOR_SHA256` to compare explicitly
selected original bytes. A fingerprint binds selection, host, collector, storage
device/inodes and all observed links, addresses, IPv4/IPv6 routes/rules and nft
structure. Only nft counter observations and known route/address lifetime fields
are omitted; quota limits and policy rules stay bound. Unknown fields are retained,
so extra changes may conservatively report drift. Incomplete inputs never produce
`local_binding_matches=true`, even when both partial snapshots are equal.

Both matching and blocked reports exit 2 and always deny network admission, caller
authorization and deployment qualification. Exit 1 denotes inspection/input failure.
Reports are exclusive mode-0600 files (maximum 32 MiB); prior inputs reject symlinks
and nonregular files, and their hashes/schema are checked before local commands.
Use a trusted private output parent. stdout contains only blockers, hashes and
comparison field names. Original addresses/rules/identities stay in ignored local
reports. No cloud, DNS, venue or packet probe is performed.

This is a non-atomic preflight observation, not an authenticated helper, live process
handle, code attestation or continuous guard. Public mapping, authorized collector
launch/IPC, complete tunnels/offload/proxy coverage, durable fixed storage and
deployment acceptance remain required. See the [binding preflight report](../../docs/progress/portfolio-egress-binding-preflight-2026-09-16.md).

## Isolated collector launcher and authenticated control channel

Run the separate bounded launcher acceptance as an ordinary user, without arguments:

```bash
/usr/bin/python3 -I infra/egress-guard/collector_launcher.py
```

It reuses `selftest.py`'s namespace-isolation checks and durable journals, plus
`inspect_binding.py`'s process metadata reader. Sources are loaded once into the
disposable worker; their hashes are reported. Before any fixture mount/nft mutation,
the worker must be in fresh user/network/mount/PID namespaces with empty topology.
Its 25-second alarm and the parent's 30-second timeout bound the run. It installs
no host service or privileged entrypoint and accepts neither supplied commands
nor real collector parameters through its public CLI.

`FixtureCollector` launches a fixed system-Python child in another fresh network
namespace, with all capability sets removed and no-new-privileges. A private Unix
`SOCK_SEQPACKET` pair is the only control channel; no filesystem socket/listener
is published. The helper holds a pidfd for its actual child. Every received frame
must carry matching kernel `SCM_CREDENTIALS` PID/UID/GID, canonical bounded JSON,
the exact operation/sequence and no extra fields. Cached socketpair `SO_PEERCRED`
identifies the creating process, so it is deliberately not used as child identity.
Passed file descriptors, oversized/truncated frames and malformed credentials
terminate the channel; any received descriptors are closed even on truncation.

The finite protocol is `ready`, at most one `observe`/`observed`, then `close`/
`closed`. There is no command, path, destination, activation or renewal operation.
The parent independently binds process metadata and launcher-source hash, verifies
pidfd liveness and metadata before/after observation, and consumes the local
attempt before sending. Failure stops processing and reaps the child; helper death
closes the channel and the child exits on EOF or its receive timeout. Process
ownership and a lock serialize normal observation/shutdown. There is no retry.

The actual isolated acceptance joins authenticated readiness to durable window
activation, then a separate journaled control observation, kernel revocation and
child teardown. Window and IPC attempts remain distinct in replay. The child has
no IP routes or transport operation; this does not exercise a real HTTP request.
The existing rootless map gives helper and child the same namespace UID 0, with
capabilities removed only in the child. It does **not** prove a dedicated host UID
or filesystem separation: the trusted fixture child could access same-UID fixture
files if its code were changed. Installed code ownership, dedicated UID/IPC policy,
fixed host storage and real source/path authority remain production work. Do not
install this test harness as a sudo helper. See the [launcher acceptance report](../../docs/progress/portfolio-collector-launcher-2026-09-16.md).

## Fixed installation authority contract

`installation.py` checks the proposed fixed host installation without creating
accounts, copying code, claiming a scope or starting a collector:

```bash
/usr/bin/python3 -I infra/egress-guard/installation.py \
  --report data/NEW-INSTALLATION-CHECK.json
```

`TrustedInstallation` opens `/etc/trader/egress-install.json`, the three fixed
source files under `/usr/local/lib/trader-egress`, and `/var/lib/trader/egress`.
It walks from `/` with held directory descriptors and no-follow opens. Every
ancestor must be root-owned without group/other write access; code files must
be regular, single-link, root-owned mode 0444 with matching hashes. The manifest
must be root-owned mode 0600 and storage a root-owned mode-0700 directory. Symlinks,
hardlinks, nonregular files and alternate source names are refused. No alternate
root, account or code path is accepted by the public CLI.

The dedicated `trader-egress` account must have nonzero UID/GID, its own named
primary group, `/nonexistent` home and `/usr/sbin/nologin` shell. UID aliases,
shared primary GIDs, group aliases, other group members and supplementary-group
membership are rejected. The root-owned manifest pins the actual numeric IDs;
none are guessed or provisioned by this checker. Password lock still needs separate
verification when the account is provisioned; this checker does not read shadow.

The installed manifest has exactly `schema_version`, `collector` and `files`.
Use schema `portfolio.egress_installation.v2`; `collector` contains exactly the
name and actual numeric UID/GID, while `files` maps `collector_launcher.py`,
`inspect_binding.py`, `installation.py` and `helper_entry.py` to their SHA256 strings. The separate
[review contract](../../docs/progress/portfolio-egress-installation-contract-2026-09-16-v3.json)
pins modes and current source hashes but is **not** the installed manifest.

Authority verification rechecks account identity, mount namespace, path/device/
inode/owner/mode and original file bytes through retained descriptors. An observed
change permanently closes the object; reverting files cannot revive it. Directory
link counts are excluded so creating an owned consumed-scope directory is allowed.
The descriptor handles use close-on-exec and are not passed to the collector.

The internal `FixtureCollector.from_installation` entry loads only verified source
bytes and binds the manifest hash into the process identity. Its dedicated branch
uses explicit `setpriv --reuid/--regid --clear-groups`, verifies all four UID/GID
values and empty supplementary groups, and expects those IDs in kernel message
credentials. Installation authority is rechecked with process identity. This is
an internal collector branch. The separate fixed `helper_entry.py --check` establishes
filesystem trust in the verifier before loading it and performs read-only checks;
it does not expose that collector branch or activation operations.

The public checker writes an exclusive private report and always exits 2 after
inspection, including when local checks pass. It never grants network/deployment
authority. Current host installation is unavailable; this session has no subordinate
UID/GID ranges or `newuidmap`/`newgidmap`. The new sudo-backed disposable acceptance
below now verifies actual distinct kernel UIDs and root-owned file protection;
the older same-UID rootless integration alone does not. See the [historical implementation report](../../docs/progress/portfolio-egress-installation-2026-09-16.md).

## Reviewable installation bundle and fixed check entry

`package.py` builds a deterministic uncompressed USTAR archive of the four fixed
sources, its own bytes as `install.py`, an inactive-phase `README.md` and the
SHA256 inventory `bundle.json`. `inspect` requires a selected whole-archive hash,
checks bounded regular members and canonical archive bytes, and never extracts
or executes them. The v2 manifest includes the new entrypoint; v1 manifests are
rejected and historical v1 contracts remain unchanged.

```bash
/usr/bin/python3 -I infra/egress-guard/package.py build --output data/NEW-BUNDLE.tar
/usr/bin/python3 -I infra/egress-guard/package.py inspect --bundle data/NEW-BUNDLE.tar --sha256 SELECTED_SHA256
```

The bundled installer's explicit `apply` is **implemented but not run on this
host**. After bundle review and host-install authorization, stage its reviewed
`install.py` under a protected root-owned directory as a single-link 0444 file,
then use `/usr/bin/python3 -I /PROTECTED/install.py apply --bundle /BUNDLE --sha256
SELECTED_SHA256`. Never elevate the mutable checkout. `apply` requires real/effective
UID 0, isolated Python, protected installer paths and exact installer bytes matching
the pinned bundle. Hash selection is the operator's trust decision, not publisher
authentication. Trusted root and system Python/libraries remain prerequisites.

The installer checks all fixed parents, rejects any existing code root or manifest,
validates/reuses a correct account or creates `trader-egress` only when both user
and group are absent, and checks its password is locked with `passwd -S`. It creates
no home/mail spool/login log entry. Sources are exclusively written/fsynced as
0444, fixed storage is created 0700 or preserved, and the root-owned 0600 manifest
is published last. The exclusive code directory marks an attempt before account
mutation. Failure after this marker blocks rerun and leaves evidence for manual
inspection; no automatic deletion, upgrade, permission repair or scope reset exists.
Missing parent directories may be created. No sudoers, services or network settings
are installed. Unit tests simulate accounts and ownership under a private filesystem
root. The successor disposable acceptance below also runs actual useradd, password
status, installed checks and distinct-UID filesystem/IPC operations.

The sole installed public operation is:

```bash
/usr/bin/python3 -I /usr/local/lib/trader-egress/helper_entry.py --check
```

It rejects checkout invocation, requires isolated Python, checks the root-owned
no-follow verifier path before executing its source, then checks the entire v2
installation. Both success and refusal return 2; all admission flags stay false.
No collection or kernel activation is possible through this entrypoint. See the
[bundle report and pinned artifact](../../docs/progress/portfolio-egress-bundle-2026-09-16.md).

## Actual disposable installation and distinct-UID acceptance

`installation_selftest.py` is an explicit sudo-backed test wrapper, run as an
ordinary user. It requires existing `sudo -n` permission; it never installs a sudo
rule, mapping helper, host account or service. It pins the corrected installer and
bundle, enters fresh private mount/network/PID namespaces, and refuses to mutate
anything unless running as namespace PID 1 with all three namespaces different.
Synthetic passwd/group/shadow files and installation/storage paths live on private
tmpfs mounts. The original host databases are never copied into the fixture.

```bash
/usr/bin/python3 -I infra/egress-guard/installation_selftest.py --report data/NEW-ISOLATED-INSTALLATION.json
```

The installed package actually creates a nonroot system user, verifies its locked
password and runs the fixed check in a fresh process. `FixtureCollector.from_installation`
then executes the dedicated-UID branch, validates kernel credentials, performs one
control observation and closes the child. A separate fixed probe running under the
same IDs with empty groups/capabilities tests readable code, denied writes/removal/
chmod, denied manifest access and denied storage read/write/delete/scope creation.
The consumed fixture bytes survive both installation and a refused second install.
Storage mode drift blocks a fresh check and permanently invalidates held authority.

The current system rejects `useradd -K CREATE_MAIL_SPOOL=no`, which the earlier
mocked tests did not reveal. `package.py` now uses supported system-user arguments.
The real test verifies no mail/login-log creation even with fixture
`CREATE_MAIL_SPOOL=yes`. The four installed sources and v2 manifest shape stay the
same; only the installer and whole-bundle hash change. Old artifacts/contracts
remain historical; use the v3 review contract linked above for the corrected bundle.

The acceptance passes **40 actual checks**. Host passwd/group hashes, fixed path
observations and caller namespaces compare equal before/after. The worker alarm is
45 seconds, command timeout 10 seconds, parent communication deadline 55 seconds;
PID-namespace teardown reaps descendants. No interface is brought up or external
request made. This qualifies the tested disposable process/filesystem boundary,
not deployment on the real host, disk/power-loss durability, complete traffic
coverage or collection admission. See the [actual acceptance report](../../docs/progress/portfolio-egress-isolated-installation-2026-09-16.md).

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
