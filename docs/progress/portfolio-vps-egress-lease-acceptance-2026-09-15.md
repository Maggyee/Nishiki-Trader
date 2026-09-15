# Isolated egress expiry and observed-loss acceptance — 2026-09-15

The existing [namespace fixture](../../infra/egress-guard/README.md) now exercises
kernel-expiring permissions and a bounded local dispatch supervisor. **20 added
Linux checks** pass alongside the original 23 checks. **30 focused Python tests**
pass, including 17 added cases. No host firewall, public route, service, source
mapping, credential or real collector was changed.

## What is verified

The new independent fixture table defaults forwarded traffic to drop. A timeout
set allows only the selected bridge's IPv4 source to reach one fixed local peer
and port. Host callers, another source and IPv6 fallback fail. With no renewal,
a two-second element expires in the kernel and blocks both new requests and
requests on an already-established TCP socket. No supervisor polling is required
for that expiry behavior. Return traffic has a separate fixed rule; this is
outbound request denial, not cancellation of in-flight responses.

The `FixtureDispatchGuard` performs serialized local preparations and requests.
Its selected identity contains the actual child namespace, client route and guard
structure. Structural comparison keeps rule handles and set members, excluding
dynamic counters/remaining expiry. The four-attempt fixture cap is independent
of the frozen 21-step collection budget; no API weights are assigned here.

Each preparation is appended and fsynced before transport. Original-file inode,
size and exact-prefix checks detect truncation, rewriting, replacement and removal.
Records carry attempt numbers, monotonic times and selected-identity/prefix hashes.
Disk errors, incomplete outcomes or observed configuration loss halt the instance;
attempts are not refunded. Post-send identity loss leaves the original preparation
uncertain. The same path cannot be reopened; there is no resume/reset method.
The exclusive-create guard is per selected path, not global scope activation.

Actual namespace acceptance covers table deletion, route/source-selection change,
audit truncation and set revocation. Each scenario first completes one fixture
request, then proves loss is detected before the next owned transport invocation.
Restoring configuration does not clear the halt. Audit paths are in a private
1 MiB tmpfs; this exercises write ordering and process-failure behavior, not
power-loss durability or authoritative gateway history.

The Python cases independently cover namespace/route/rule changes, audit damage,
preparation/outcome fsync errors, changes during preparation, transport failure,
uncertain results, post-send changes, serialized concurrent requests and the fixed
attempt bound. A separate process exits abruptly during its transport callback;
only its prepared event remains and exclusive creation on that path is refused.
No real venue or credentials are used by these tests.

## A verified limit, not a closed race

The fixture also deletes the guard table **after the final observation and before
the transport sends**. One request reaches the local echo peer. The subsequent
check detects the missing table and leaves the preparation uncertain, with the
supervisor halted. This explicitly demonstrates that observation checks cannot
prevent every send under uncontrolled privileged network changes.

The report therefore keeps `uncontrolled_rule_mutation_race_closed`,
`gateway_coverage_qualified` and `capture_admitted` false. The nft timeout mechanism
does not fix arbitrary table deletion; a post-send check cannot retract traffic.
These fixtures are evidence for a trusted controller/transport design, not a
complete all-caller lease or a claim of complete API attempt accounting.

## Next entrypoint and boundaries

Bind actual source authorization, namespace ownership and route/cloud mapping to
a trusted network controller and the dispatch transport. Policy changes and
shutdown must be coordinated with that transport. Persistent audit/restart
semantics and complete coverage of applicable callers remain necessary; the
fixture's private tmpfs is not a deployment backend. Public-source selection and
Docker/Tailscale/UDP/proxy integration remain unimplemented.

The separate first-request issue is unchanged: current draft requires fresh
pre-existing authenticated usage and applicable limits before the first GET.
Those records remain unavailable. Obtain qualifying evidence or define a separate
prospective bootstrap contract; do not silently revise the frozen draft, wait out
a window and assume zero, or issue a seed probe. Unspecified market-WS connection
weight remains a blocker. Consumed ADR-017/public-depth scopes stay consumed;
full-account/UTC/flow/reset qualification and strict continuity **0/14** remain.

## Verification

The full standalone fixture was run on this VPS as the ordinary `orca` user with
system Python 3.10. Its JSON stdout is retained privately under
`data/vps-egress-lease-2026-09-15.json`; no raw host configuration is committed.
The report SHA256 is
`d3f2a5d9a890b7cf2b14135b284f13473a7048bcb646b85410d1c3d31333daad`;
the tested script SHA256 is
`1803a8dea35f6cb6995b659d9532f81f73809f6db1d947c7d8b22e8c22d8d98e`.
Read-only sudo snapshots before/after confirm unchanged host nftables structure
excluding counters and metadata; host IPv6 forwarding is unchanged. Ruff,
focused tests, documentation links and diff checks pass; the frozen capture JSON
SHA256 remains `91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
Historical full application regression was not rerun for this standalone fixture.

Changed files: the existing fixture and tests, its README, this report,
`docs/agent-reading-list.md` and `docs/project-status.md`. No upstream source or
live trading path was touched. No production deployment or venue request occurred.
