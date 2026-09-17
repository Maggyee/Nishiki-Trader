# Durable gateway lifecycle and controller crash acceptance

Date: 2026-09-17. Isolated local fixtures only; no venue requests or deployment.

The [ledger gateway](portfolio-egress-ledger-gateway-2026-09-17.md) now retains an
independent kernel lifecycle journal alongside its attempt ledger. Previously,
activation and revocation existed only in controller memory. After a crash, the
attempt archive could retain an uncertain request but could not distinguish a
prepared activation from an acknowledged grant or an unacknowledged revocation.
`infra/egress-guard/ledger_gateway.py` now persists these distinctions and exercises
controller SIGKILL with actual nftables timeout enforcement.

## Ordering and failure behavior

The exclusive `kernel.jsonl` belongs to the already consumed private attempt scope.
It reuses the bounded, fsynced hash-chain writer and validates the original ledger
storage plus its own inode, ownership, mode, link count and exact retained prefix.
There is no reopen, resume, reset, renewal or alternative journal filename API.
This remains caller-selected disposable storage, not fixed host authority.

For the one authenticated fixture operation, the gateway:

1. Persists the original pending attempt and verifies its borrowed binding.
2. Persists `activation_prepared`, selecting the exact pending attempt prefix,
   fixed socket mark and five-second TTL.
3. Rechecks the binding and stop flag before invoking the kernel grant.
4. Persists `activated` only after the grant returns, then rechecks before sending.
5. Records the transport outcome through the existing attempt ledger.
6. Persists `stop_requested`, attempts and verifies kernel revocation, then persists
   `revoked`. Stop and dispatch retain the same serialization lock.

A lifecycle write/fsync failure prevents progress to later grant/send steps.
Failure to persist stop intent still executes kernel revocation in `finally`.
Failure to persist its acknowledgement cannot become a durable revocation claim.
A failed kernel revoke cannot record success; no automatic retry is introduced.
Uncertain/failed attempts remain consumed, including when activation never happened.
The old callback-only unit interface remains available; the actual namespace
harness always supplies the durable lifecycle component.

The offline `replay_lifecycle` function validates canonical bytes, hash links,
clock continuity, transitions, binding selection, mark/TTL and the referenced
collector REST preparation in the original attempt archive. It rejects a prefix
that lacks a pending preparation or occurs after the activation record. Both full
and incomplete histories always return unknown `current_kernel_permission` and
false restart, complete coverage, network and trading admission. Recorded past
revocation is not proof of current kernel state. A selected/rehashed prefix cannot
prove absence of later records or establish independent source provenance.

## Actual crash results

The same rootless, no-argument namespace harness now exports ten scenarios.
The six original success/stop/drift/fsync cases still pass with both journals.
Four additional controllers are killed with SIGKILL, without executing cleanup:

| Kill point | Last durable lifecycle record | Permit observed after death | Attempt outcome |
|---|---|---|---|
| Before grant | `activation_prepared` | Absent | Pending/uncertain |
| After grant, before acknowledgement | `activation_prepared` | Present until timeout | Pending/uncertain |
| After acknowledgement, before send | `activated` | Present until timeout | Pending/uncertain |
| After verified revoke, before acknowledgement | `stop_requested` | Absent | Succeeded |

The two records ending at `activation_prepared` are intentionally indistinguishable
in replay despite different kernel observations. Likewise `stop_requested` alone
cannot prove revocation, even where the acceptance parent observed an empty set.
For every crash, a trusted marked diagnostic sender is rejected after the timeout
(or immediately when absent), and the intended OUTPUT deny counter increases.
The parent never flushes the crashed controller's permit to manufacture expiry.
Every original scope refuses reopening. Kernel timeout is a bounded fallback,
not instant revocation at controller death. No collector receives a marked socket.

The worker/parent deadlines are now 70/75 seconds to accommodate expiry checks;
process-group cleanup and initial empty-topology isolation checks are retained.
All rules, routes, processes and storage are disposable. The deny table stays
present during crash checks. The harness does not access real host accounts,
credentials, consumed bootstrap storage, external routes or venue endpoints.

## Verification and retained evidence

**28 additional / 331 focused Python tests; 29 actual kernel checks pass.**
New tests cover fsync-before-grant/ack-before-send ordering, all four lifecycle
persistence failures, kernel revoke failure, storage replacement/tampering/link
changes, rehashed semantic corruption, incomplete-prefix uncertainty and
stop/binding drift during activation persistence. Five independent disk-backed
SIGKILL stages each pass two fresh-process replays and scope-reopen refusal.
Those disk tests use fixture callbacks; actual kernel crashes use private tmpfs.
Neither establishes filesystem power-loss or rollback durability.

Each of the ten retained kernel archives is also replayed in two fresh isolated
system-Python processes; both result files are byte-identical and match the worker's
attempt and lifecycle reports. Exact originals, source copies, replay driver and
selections live under `data/egress-gateway-lifecycle-2026-09-17/`. Their SHA256 pins
and scenario summaries are in the [result JSON](portfolio-egress-gateway-lifecycle-2026-09-17.json).
Run the retained historical replay with:

```bash
/usr/bin/python3 -I data/egress-gateway-lifecycle-2026-09-17/replay.py
```

The focused regression covers the gateway, attempt ledger, existing guard,
collector authentication, authority binding and TLS persistence suites. Ruff,
format, document links, retained pins and `git diff --check` pass. The full
application suite and unchanged older kernel scripts were not rerun. An initial
unit test checked journal exclusivity after closing the underlying ledger's file
descriptors; it was corrected to check exclusivity while its owner is still open.

## Remaining boundary and next step

Next integrate this socket/lifecycle model with fixed installed source custody,
dedicated UID and fixed storage authority in the disposable installation profile.
That integration is still pending; this change does not deploy or alter a service.
Arbitrary privileged rule changes, complete shared-IP caller coverage, real quota
bounds, provider clock freshness and unknown-charge resolution remain unqualified.
The consumed one-shot bootstrap cannot reopen, the frozen joint budget remains
17 GETs / 468 documented weight, strict continuity stays 0/14 and trading is blocked.

Upstream source and the live order path are untouched. Project status, reading
index and infrastructure README are updated; detailed history is retained here.
