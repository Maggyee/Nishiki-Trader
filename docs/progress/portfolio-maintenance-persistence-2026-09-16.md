# Durable maintenance-window activation acceptance

The existing-IPv4 maintenance fixture now **persists window consumption before
enabling kernel permissions**. This closes the isolated fixture's activation-order
gap recorded in the [previous report](portfolio-maintenance-window-2026-09-16.md).
The historical proposal and JSON are unchanged. This remains offline acceptance:
no host rules, proxy settings, real collector or venue transport were changed.

## Persistence and failure behavior

`PersistentFixtureMaintenanceWindow` composes the existing kernel window with a
separate `WindowActivationJournal`. The fixed directory is `fixture-window-v1`,
distinct from the request controller's `fixture-scope-v1`; they can share one
private root without confusing a kernel activation with a request dispatch.

Before kernel activation, the wrapper exclusively creates the scope, fsyncs the
root and journal directory entries, writes/fsyncs the storage-claim record, then
writes/fsyncs a single preparation. The inherited serialized controller verifies
identity and original journal bytes around preparation and the kernel operation.
The identity includes the profile, bounded timer settings, literal rules SHA256
and selected fixture namespace, route, NAT and guard structure. Only owned timer
memberships are excluded from the window binding, since activation changes those;
the request journal still binds the active membership and detects expiry on resume.

Initialization failure leaves the directory consumed. Failure to persist
preparation invokes no kernel operation. Once activation is attempted, failure
halts and attempts terminal cleanup even if audit writes fail. An uncertain
preparation is never refunded, renewed or upgraded to success by cleanup. All
fresh initializers refuse an existing scope, including empty and terminal ones.
This uses the existing trusted caller-selected storage root; it is not a global
authority preventing another root, privileged deletion or restored backups.

Read-only `review_window_activation` validates identity, hash-selected original
bytes, lifecycle and the one-preparation bound. Its terms are deliberately narrow:

- `activated` means the storage claim, before any kernel permission.
- `kernel_activation_return_recorded` means the command returned and the selected
  observation still matched; it does not prove continuous enforcement or API usage.
- `uncertain_kernel_activation` means the preparation has no result record. The
  kernel may or may not have applied the operation.
- `cleanup_recorded` means terminal cleanup returned; with zero preparations it
  is a no-op closure, not evidence of a kernel revoke.
- Restart, capture admission and gateway coverage remain false in every report.

The default limits remain 12 seconds for collector permission and 20 seconds for
other-caller blackout. Ordered kernel expiry remains the crash fallback. There is
no retry, renewal, resume or host installation API.

## Verification

**151 actual Linux checks and 149 focused Python tests pass**, adding 11 kernel
checks and 23 Python cases to the prior result. All older isolated hook, lease,
controller, SNAT/proxy and maintenance checks remain included.

The namespace harness verifies preparation before actual nft activation, normal
terminal replay and unchanged bytes after reopening refusal. A new abrupt-exit
case stops immediately after actual kernel activation, before its result record
and before any request journal. Its activation remains uncertain, the collector
loses permission first, ordinary direct/proxy traffic later resumes and the
collector stays quarantined. Existing crash-after-send and SIGSTOP/resume cases
retain separate activation and uncertain-request histories.

The disk tests use independent system-Python processes and simulated kernel calls
at six crash points: scope creation, storage claim, preparation, kernel operation,
recorded result and terminal cleanup. Each available journal produces identical
reports in two fresh processes. A further fresh initializer always refuses the
scope without changing retained bytes or issuing another kernel call. Scope-only
crashes retain the directory even when no journal exists. Other cases cover fsync
failures, identity drift, duplicate activation, audit-loss cleanup and invalid
window replay identities/lifecycles.

Commands:

```bash
/usr/bin/python3 -I infra/egress-guard/selftest.py
uv run pytest -q tests/ops/test_egress_guard_selftest.py tests/ops/test_egress_host_inspection.py
uv run ruff check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
uv run ruff format --check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
```

Kernel-tested source SHA256:
`75ba8a36ca075f4236f20e68524117bf1abc1431226271bb0df35912c4ebff5f`.
Ruff/format, local links, frozen prior artifacts and diff checks pass. Full
application regression was not rerun for this standalone infrastructure fixture.
Process-exit persistence and fsync ordering do not establish host power-loss,
VM-restart or filesystem-rollback guarantees. Selected hashes are not historical
source provenance, and privileged mutation races remain outside the guarantee.

## Next implementation boundary

Continue with actual source/caller authorization, complete external-path coverage
and a fixed trusted storage contract, then a separately reviewable privileged
helper and rollout/rollback procedure. The current optional sudo rule permits
reading host rules only. Real host deployment still requires explicit acceptance
of the proposed interruption and out-of-band recovery; no interruption is accepted
by this offline implementation.

The separate single-GET bootstrap remains Draft and unimplemented. Its deadline
must fit the remaining permission after activation/setup; a late start must abort,
never extend the window. The window cannot establish unknown prior shared-IP usage
or activate the frozen 17-GET / 468-weight joint capture. Existing ADR-017 and
public-depth scopes remain consumed, strict continuity remains **0/14**, and live
trading stays blocked. No upstream source or live execution path was touched.
