# Isolated egress hook acceptance

Purpose: exercise OUTPUT/FORWARD hooks, expiring permissions, observed-loss
refusal and fixed-scope journal persistence in disposable Linux namespaces and
offline disk tests, and retain read-only host deployment-input snapshots.
Current phase: Phase 5 entry, offline infrastructure acceptance only. This is not
a production guard, gateway audit service, quota authority or collection permit.

The signed account successor is `gateway_account_ws.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --signed-ws-profile --report data/NEW-SIGNED-WS.json
```

The consumed six-read route parent owns a separate `signed-account-ws-v1` scope.
One isolated native child signs the public fixture subscription; root validates
and persists its exact masked frame before send while the market channel remains
open. Original subscription response and one partial account update precede both
close handshakes and kernel revocation. Only then does native AccountBalance
construction acknowledge the exact payload. Missing/late acknowledgements remain
incomplete and cannot resume. Partial updates do not imply a full snapshot or fence.
Manifest v12 pins nineteen sources; the base v2 bundle and 1,024 descriptor limit
are unchanged. Next integrate market/depth event delivery and concurrent REST/depth.
See [signed WS acceptance](../../docs/progress/portfolio-installed-signed-ws-2026-09-22.md).

The preceding control-only profile is `gateway_concurrent_ws.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --concurrent-ws-profile --report data/NEW-WS.json
```

It consumes the six-read route parent and then its nested `concurrent-ws-v1` scope;
a fresh process cannot reopen either. Before either connection, the controller
persists both fixed account/market connection attempts and one kernel activation
intent. Two gateway-owned marked TLS sockets share one nonrenewable five-second
permit and a four-second total I/O deadline measured before grant. The market
Upgrade URL uses only the symbol union rederived from original route bytes.
TLS hostname/CA verification, exact HTTP Upgrade, ping/pong and close handshakes
are replayed from original chunks. One channel's failure cancels its sibling;
cleanup attempts kernel revocation even after storage or socket-close failure.
This preceding profile performs no signing or account event delivery.

The frame parser is now importable using stdlib alone; native depth mapping keeps
the same shared exception/limit. Explicit byte order and compatible asyncio APIs
support the system Python 3.10 used by the root fixture controller. The current manifest v12
pins nineteen sources; the base installation bundle remains unchanged.
See [concurrent upgrade/control acceptance](../../docs/progress/portfolio-installed-concurrent-ws-2026-09-19.md).
The signed account successor above extends these channels; complete concurrent
REST/depth collection remains pending.
Host installation, real venue requests and all consumed real scopes are unchanged.

`TrustedInstallation` now owns one descriptor per canonical selected directory or
file path, including shared ancestors. `open_directory` and `open_file` return
borrowed handles valid until installation close; callers must not close them.
Each borrow rechecks held path identity, bytes, ownership/mode, account and mount
namespace. File reborrows must use the original mode. Observed drift or a failed
new acquisition permanently closes the authority, without reopening it; foreign
processes cannot borrow or close the original owner's handles. No-follow opens,
single-link regular-file checks and the base v2 manifest inventory remain intact.

In disposable six-read acceptance, the maximum sampled controller count falls
from 1,009 to 844 under the unchanged 1,024 descriptor limit. Activation and
pre-receipt samples must leave at least 64 descriptors spare. This measures sampled
headroom, not continuous peaks or concurrent socket capacity. The updated base
bundle pin selects the revised verifier in disposable namespaces only; no host
helper rollout occurred. Supplemental manifest v12 now pins nineteen sources.
See [descriptor custody acceptance](../../docs/progress/portfolio-installed-descriptor-custody-2026-09-19.md).
The concurrent upgrade/control successor above is now integrated; the signed/partial native event successor is described above.

The six-read route profile adds `gateway_book_routes.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --route-sequence-profile --report data/NEW-ROUTES.json
```

The distinct `fixture-route-sequence-v1` scope appends one fixed unsigned bookTicker
GET to metadata/account/orders/orders/account (six GETs / 224 documented weight).
Its native request selector, original TLS and exact native Price/Quantity receipt
use the existing isolated channel and revocation boundaries. No QuoteTick or event
time is fabricated. Root replays the same-run metadata original and native balances
and books to select direct-then-two-hop routes to USDT, preserving zero balances.
Every nonzero nonquote asset needs a supported route and sufficient capacity at each
leg. Choice uses fixed shortest/lexical priority, never the best price; capacities
use exact rational arithmetic. The selected symbol union is capped at three.

The four fixture assets, eight-place precision, sixteen metadata/book rows and
60-second same-UTC-day input interval are fixed. Original clocks remain original;
book age, stream continuity, equity and dispatch remain unqualified. The current manifest v12
pins nineteen sources; the old three/five-read profiles stay distinct. See
[route acceptance](../../docs/progress/portfolio-installed-route-sequence-2026-09-19.md).
The concurrent upgrade/control successor above consumes these selected symbols; the signed/partial native event successor is described above.

The five-read successor adds `gateway_native_orders.py` to `gateway_read_sequence.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --order-sequence-profile --report data/NEW-ORDERS.json
```

The separate `fixture-order-sequence-v1` scope fixes metadata → account → openOrders
→ openOrders → account (five GETs / 220 documented fixture weight). The dedicated
UID signs each private read and maps open orders to actual native OrderStatusReport
objects; root owns TLS and revokes permission before receipt delivery. Supported
orders are fixed-symbol LIMIT/GTC, NEW or PARTIALLY_FILLED, at exact eight-place
native precision. Repeated orders and balances must agree, and remaining BUY quote
and SELL base locks must exactly account for every asset's locked balance. Empty
orders require zero locks. No fill/fee history or atomic stream fence is inferred.
Manifest v12 pins nineteen sources. The old three-read profile remains distinct.
See [order acceptance](../../docs/progress/portfolio-installed-order-sequence-2026-09-18.md).
The successors above derive routes and accept concurrent TLS/WS Upgrade/control exchanges.

The fixed repeated-read successor is `gateway_read_sequence.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --read-sequence-profile --report data/NEW-SEQUENCE.json
```

One root controller sequences metadata and two signed account reads, using a fresh
isolated native child and the existing one-shot TLS/receipt machinery per step.
The exclusive parent journal binds original preparations and native acknowledgements;
each kernel permit is revoked and the child ledger closed before the next step.
Metadata precision must match the four-asset mapper, and repeated free/locked/total
balances must agree exactly. Drift or missing receipts never permit a resume.
Manifest v12 pins nineteen sources; held original paths reuse descriptors without
raising system limits. See [sequence acceptance](../../docs/progress/portfolio-installed-read-sequence-2026-09-18.md).
The successors above add open orders, same-run routes and concurrent TLS/WS Upgrade/control exchanges.
This fixed fixture does not qualify an atomic snapshot, account stream fence,
provider quota, real account/equity or execution.

The signed account successor is `gateway_native_account.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --signed-account-profile --report data/NEW-ACCOUNT.json
```

It joins one isolated native Ed25519 request to the root-owned local HTTPS socket,
then delivers original response bytes/clocks for actual native AccountBalance
construction. Root validates the fixed GET, public fixture key and original signing
window; verifier time reduces the remaining connect/write allowance. The separate
account ledger binds the request digest and a pinned `account-request.json` original.
Kernel permission is revoked before consumer delivery; any native Money rounding
or missing final receipt keeps the attempt pending. Account header usage is retained
without fabricating exchangeInfo rate limits. The four fixture assets/precision are
fixed, and no actual account, route, WS, equity or trading qualification follows.

Supplemental manifest v12 pins nineteen sources. The base installation/launcher and
prior journal profiles remain separate. Seven actual account scenarios plus 42
regressions and detached original/native replays are recorded in
[signed account acceptance](../../docs/progress/portfolio-installed-signed-account-2026-09-18.md).
The successors above join repeated reads, original-derived routes and concurrent
TLS/WS Upgrade/control exchanges. The signed/partial native event successor is described above.

The native request custody successor is `gateway_native_requests.py`:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --native-requests-profile --report data/NEW-REQUESTS.json
```

It reuses the frozen native child runtime and exact PID/UID/GID credential channel.
The isolated child emits 20 fixed request envelopes, including eight REST signatures
and one signed WS subscription using Nautilus Ed25519 and the public RFC 8032 test
key. Root uses system OpenSSL with anonymous file descriptors to verify signatures,
compares exact methods/paths/parameters and original challenge clocks, and persists
request hashes before acknowledgements. The fixture budget stays 16 GET selectors /
448 documented weight with unknown market-connection charge. No kernel grant or
request dispatch follows. Fixed BTC/ETH/BNB routes and subscription ID zero are
synthetic selections, not values derived from actual same-run responses.

The current manifest v12 pins nineteen protected sources. The separate request ledger/scope and
`requests.jsonl` preserve incomplete attempts after drift, consumer death or root
crash. Detached replay verifies signatures and receipt ordering with original times;
it never refreshes expiry or repairs missing acknowledgements. The successors above
connect account/routes, concurrent Upgrade/control and signed partial WS delivery;
market/depth and full joint collection remain pending. See [request acceptance](../../docs/progress/portfolio-installed-native-requests-2026-09-17.md).

The native metadata successor adds `gateway_native_runtime.py` and
`gateway_native_receipt.py`. Run the existing disposable wrapper as an ordinary user:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --native-receipt-profile --report data/NEW-NATIVE.json
```

The wrapper freezes the project CPython 3.12/Nautilus 1.226.0 runtime before sudo,
retaining a `.runtime.tar.gz` beside the report. Only the isolated dedicated UID
imports Nautilus and constructs BTC/ETH/BNB/USDT Currency objects from the original
root HTTPS bytes. Its final acknowledgement binds both the native summary and the
original payload, including original receive clocks. Root parses the expected
summary with stdlib only. Protected fixture manifest v12 pins nineteen sources;
base installation and earlier journal profiles remain separate.

The private runtime tmpfs is root-owned and read-only. Files are fully hashed at
startup, held open, then checked for path/inode/metadata and mount changes during
use; this is not continuous content rehashing or qualification of arbitrary OS
libraries or concurrent root administration. Native precision rejection, remount
drift, stopped consumers and crashes retain missing receipts and pending attempts.
This implements one fixed local metadata GET only. The next entrypoint is full
native signed REST/account/route/WS integration; no host rollout or real request
is enabled. See [native acceptance](../../docs/progress/portfolio-installed-native-receipt-2026-09-17.md).

The response-delivery successor is `gateway_tls_receipt.py`, selected by
`installed_gateway_selftest.py --tls-receipt-profile --report data/NEW-RECEIPT.json`.
One fixed exchangeInfo request is authenticated before accounting and root-owned
TLS. Original response bytes and root receive clocks reach the isolated stdlib
consumer over the unchanged credential-framed channel. Kernel permission is revoked
before delivery; a missing final digest acknowledgement keeps the attempt pending.
The separate receipt journal binds original attempt, kernel and TLS records.
The base installer/launcher and old profiles remain unchanged. This runs only in
disposable namespaces; native joint REST/WS integration remains the next entrypoint.
See [response acceptance](../../docs/progress/portfolio-installed-tls-receipt-2026-09-17.md)
and the [deadline/replay review](../../docs/progress/portfolio-installed-tls-receipt-review-2026-09-17.md).
The reviewer enforces a single attempt and active preparation prefix; the consumer
rechecks its total deadline after parsing and before sending acknowledgements.
The [stall review](../../docs/progress/portfolio-installed-tls-receipt-stall-2026-09-17.md)
also verifies send/receive share the remaining time, terminal records follow the
transfer and an actually stopped consumer is killed/reaped after timeout.

The installed multi-operation IPC successor is `gateway_joint_ipc.py`, selected by
`installed_gateway_selftest.py --joint-ipc-profile --report data/NEW-IPC.json`.
It reuses the pinned child launcher and per-message credentials, then durably
consumes 20 fixed operation classifications in a separate root-owned scope before
acknowledgement. It never grants a mark or performs IP transport. Next connect the
actual native collector, signed selectors and gateway-owned TLS/WS sockets through
this boundary. See [IPC acceptance](../../docs/progress/portfolio-installed-joint-ipc-2026-09-17.md).

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

## Prospective ledger gateway integration

Run the separate rootless acceptance with no arguments:

```bash
/usr/bin/python3 -I infra/egress-guard/ledger_gateway.py
```

It reuses the attempt ledger and authenticated collector launcher inside fresh
namespaces. The trusted gateway owns its fixed local echo socket; durable
preparation precedes a five-second mark permission, while all forwarding and
unmarked output remain denied. The child receives no socket/destination authority.
Managed stop, observed drift and fsync failures prevent later sends and attempt
terminal revocation. Ten fixture scenarios export exact attempt and kernel
journals for offline replay.
A separate exclusive `kernel.jsonl` records activation intent before grant,
acknowledgement before send, stop intent and verified revocation. It binds the
original pending attempt prefix, mark and five-second TTL. Audit failure cannot
skip revocation; missing acknowledgements stay uncertain. Four SIGKILL stages
verify actual expiry without controller cleanup and refusal to reopen the scope.
The worker/parent deadlines are 70/75 seconds. No replay infers current permission.
This is not an installed helper, HTTP collector or complete shared-IP accounting.
The installed successor below integrates UID/storage authority in disposable
acceptance; host deployment and power-loss/rollback durability remain pending.
See the [original gateway report](../../docs/progress/portfolio-egress-ledger-gateway-2026-09-17.md)
and [lifecycle acceptance](../../docs/progress/portfolio-egress-gateway-lifecycle-2026-09-17.md).

## Fixed installed gateway and dedicated UID

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --report data/NEW-INSTALLED-GATEWAY.json
```

The ordinary-user wrapper uses existing sudo to run five fresh private mount,
network and PID namespaces. It reuses the pinned installer, then stages a separate
fixture v8 manifest and fourteen protected sources in the disposable installation. The
fixed installed `installed_gateway.py --fixture` entry consumes the original
fixed storage scope, authenticates the distinct-UID child and uses the durable
kernel lifecycle. Neither the collector nor the public wrapper can select another
scope, endpoint or payload. No gateway extension is installed on the host.

Actual permission attacks, code/account/storage drift, SIGKILL expiry and fresh
installed-process scope refusal pass. Offline replay never reconstructs installed
authority or grants restart. The TLS successor below adds one fixed HTTPS request;
provider/source policy and complete all-caller coverage remain blocked.
See the [installed integration report](../../docs/progress/portfolio-egress-installed-gateway-2026-09-17.md).

## Fixed HTTPS request and original counter receipt

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --tls-profile --report data/NEW-GATEWAY-TLS.json
```

The explicit TLS fixture uses the same fixed installation, dedicated child and
consumed storage. `gateway_tls.py` owns the marked socket to the reserved local
peer, verifies protected fixture trust and sends only the fixed unsigned
exchangeInfo GET. Its exclusive TLS journal references the original pending attempt
and activated kernel prefixes. Raw response chunks precede parsing; their receipt
clocks precede even disk validation, so delayed body completion never refreshes a
header counter. The base loopback-only TLS APIs and real capture scopes are unchanged.

Six actual TLS scenarios include wrong certificates, duplicate counters, truncated
bodies and SIGKILL after headers. Two independent offline replays retain unknown
usage/connection charges and false network/trading admission. The next entrypoint
is bounded multi-operation joint transport with per-operation gateway accounting.
See the [TLS integration report](../../docs/progress/portfolio-egress-gateway-tls-2026-09-17.md).

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

## Actual host installation and authorized one-shot bootstrap

`host_acceptance.py` performs root-staged acceptance of the installed authority,
actual dedicated UID, filesystem denial, one IPC observation and fresh-process
consumed-record replay. Its acceptance scope is separate from real capture.

`bootstrap_once.py` is the reviewed fixed public GET runner, installed separately
as root-owned read-only code under `/usr/local/lib/trader-egress-bootstrap-v1`.
A protected plan pins the source commit, code/parser/CA, installed account/manifest,
boot/MAC and fresh literal endpoint. `/var/lib/trader/egress/rest-bootstrap-v1`
is permanently consumed before topology or any venue socket. It never retries.
The child has UID 997, no capabilities/groups, verified TLS and a credential-bound
IPC channel; root fsyncs received chunks before acknowledging interpretation.

The operator accepted one maximum 20-second ordinary-IP interruption and 12-second
collector allowance, including unknown prior usage for one exchangeInfo GET.
Independent inet OUTPUT/FORWARD and WAN netdev egress guards cover raw IPv4/IPv6.
Narrow temporary FORWARD rules traverse Docker's default drop policy. ARP/LLDP
remain usable. Kernel TTL restores ordinary traffic even after root helper death,
while the collector stays blocked. Successful cleanup removes only owned rules,
namespace and veth; no service shutdown or new recurring service is installed.

`bootstrap_selftest.py` exercises this exact runner in private mount/network/PID
namespaces with a local TLS peer, normal/raw-IP competitors and forced termination.
`apps.ops.portfolio_rest_bootstrap_review` reviews pinned original bytes offline.
See [current report](../../docs/progress/portfolio-egress-host-bootstrap-2026-09-16.md)
and [accepted contract](../../docs/progress/portfolio-shared-egress-bootstrap-2026-09-16-v2.json)
for state, hashes and the next entrypoint. Never repeat the real execute command
when status is uncertain; inspect the fixed scope and expiry instead. Existing
joint draft, consumed trading/depth scopes and live-order path stay unchanged.

Actual execution is now complete: see the
[result](../../docs/progress/portfolio-egress-bootstrap-result-2026-09-16.md).
HTTP 200, one GET, no retry; all owned network resources removed and existing
services active. The fixed real scope is permanently consumed. The next entrypoint
is offline original-evidence review; do not invoke `--execute` again.

## Local root custody and source-route binding

`authority_binding.py` joins the existing installed verifier with held descriptors
for the fixed consumed bootstrap originals, deployed runner/parser/CA, account,
boot/namespaces and current structural network. File checks bracket read-only local
network observations; any observed drift permanently closes the binding. Original
hashes are selected explicitly; a second process can require an earlier fingerprint.
There is no dispatch/signing/reset API and reports cannot recreate authority.

Actual root-staged verification now passes in two independent processes, with a
wrong expected binding refused. See the
[acceptance report](../../docs/progress/portfolio-local-authority-binding-2026-09-16.md).
Current local custody does not qualify provider/gateway authority, continuous
coverage or future enforcement. Next entrypoint: prospective all-caller accounting
and dispatch checks bound to protected local state; no new maintenance is activated.
