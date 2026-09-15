# Isolated controller ownership and terminal revocation — 2026-09-15

The [egress fixture](../../infra/egress-guard/README.md) now separates a trusted
network controller from clients without namespace-administration capabilities.
It serializes terminal permission revocation with request dispatch. **Nine new
Linux checks pass, 52 total; ten new Python cases pass, 40 total.** No host guard,
public route, cloud resource, daemon or testnet collector is deployed.

## Controlled behavior

`ControlledFixtureGuard` shares the dispatch lock with shutdown. Shutdown sets
a stop event before waiting for the lock: the current request may complete,
but queued/new requests fail. It records the stop, flushes and checks the
permission set, then records revocation. The default-deny table stays installed.
This is a terminal transition; there is no live replacement/renewal/reactivation
API. The existing four-attempt local fixture bound is unchanged.

Observed/audit/transport failure also attempts revocation. An audit write failure
cannot suppress the kernel operation; a failed kernel operation never becomes
a successful revocation or an automatic retry. Existing lease expiry remains a
fallback. Journal closure is serialized and idempotent. PID ownership is checked
before acquiring the lock, preventing a fork-inherited controller from dispatching
or waiting forever on an inherited lock.

Each client/server child enters its own network namespace, then `setpriv` drops
its effective/permitted/inheritable/ambient/bounding capabilities and sets
no-new-privs before Python starts. The worker still configures the topology through
its own capabilities. Actual sender attempts to delete its route or enter the
worker's network namespace are denied by the kernel.

The nine new Linux checks verify:

- Empty sender capability sets plus no-new-privs; route modification and controller
  namespace entry are refused (three checks).
- A concurrent managed revocation waits for the current local send, rejects the
  queued send, preserves preparation/result/stop/revoked audit order, and leaves
  the raw sender blocked by the kernel (four checks).
- A separate controller process exits abruptly during its transport callback:
  the prepared record remains and the kernel rejects the raw sender after the
  two-second lease expires without renewal (two checks).

Ten added Python cases cover shutdown before first dispatch, concurrency and
queued sends, audit/fsync/transport failures during automatic revocation,
revocation failure without retries, repeated closure and inherited-PID refusal.
Existing 43 Linux and 30 Python checks continue to pass, including the deliberately
uncontrolled privileged-deletion race. The entire script runs without host sudo.

## Limits and next entrypoint

`managed_revocation_serialized` is true for this fixture. This does **not** close
arbitrary administrator mutations: `uncontrolled_rule_mutation_race_closed`
remains false, and the old race still demonstrates one uncertain local send.
Capability dropping prevents the tested administration operations but does not
make all possible clients' requests pass through a journal. The fixed client
command channel and controller are trusted; there is no authenticated public IPC,
per-request kernel quota accounting or global caller roster.

Controller death leaves a bounded residual permission window until TTL expiry;
it does not immediately retract all traffic. The local journal lives on private
tmpfs and supports the tested process-exit evidence, not host power-loss recovery.
A stopped instance cannot restart and original-file creation remains exclusive;
no production restart/activation contract is implemented.

Next bind an actual public source and authorized callers to this ownership
boundary, implement persistent audit/restart semantics, and resolve first-request
evidence or a separate prospective bootstrap policy. IPv4-only fixture source
selection is not Oracle source mapping; Docker/Tailscale/UDP/proxy coverage remains
separate. The frozen 17-GET / 468-documented-weight draft and unknown market-WS
connection charge remain unchanged. No seed probe, new order, joint capture,
baseline qualification or reuse of consumed ADR-017/public-depth scopes follows.
Strict continuity stays **0/14**; all real admission flags remain false.

## Verification and changes

The final ordinary-user Linux run uses system Python 3.10 and existing utilities.
Its original JSON stdout is saved as ignored, mode-0600
`data/vps-egress-controller-2026-09-15-v2.json`. A read-only sudo host rules check
matches the retained September 15 snapshot after excluding counters/metadata;
no fixture tables appear on the host and host IPv6 forwarding remains disabled.
Ruff lint/format, 40 focused tests, local documentation links, diff checks and
the unchanged frozen capture JSON hash pass. The historical full application
regression was not rerun for this standalone fixture.

Final tested script SHA256:
`b8747c8cf2e90f53265acb4f36f431f41e12fbbd72e04fb5c4a4932475c893a4`.
Retained report SHA256:
`03c0bb1167d8c9bd5cb768dacd9df3bc88cb8998ad2772bd4d997ed9d231a1b2`.

Changed files: `infra/egress-guard/selftest.py`, its README,
`tests/ops/test_egress_guard_selftest.py`, this report,
`docs/agent-reading-list.md` and `docs/project-status.md`. No upstream code or
live order path changed. No credentials or raw host rules are committed.
