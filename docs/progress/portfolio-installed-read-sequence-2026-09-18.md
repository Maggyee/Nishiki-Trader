# Installed metadata and repeated account sequence

Date: 2026-09-18. Phase: disposable local fixture integration. This follows the
[signed account exchange](portfolio-installed-signed-account-2026-09-18.md).
Exact selected sources, reports, runtime and replay pins are in the matching JSON.

## Result and boundaries

One root controller now runs a fixed sequence of three local HTTPS reads:
`exchangeInfo → account → account`. Each step launches a fresh isolated dedicated-UID
Nautilus consumer. Metadata constructs native Currency objects; each account step
creates a fresh native Ed25519 request and exact AccountBalance objects. Root
imports no Nautilus package. The existing individual TLS, request and receipt
formats are reused without changing their deadlines or granting socket access to
the child. The supplemental fixture manifest is v8 with fourteen protected sources.

Before the first account read, the parent checks that the actual acknowledged
metadata selects exactly the four fixture assets and eight-place precision used by
the native account mapper. After the second account read, it compares the original
UID and all free/locked/total amounts, including zero balances, using Decimal
values. Alternate decimal spellings do not imply a changed balance. A precision
mismatch or differing endpoint balances refuses collection completion. An account
step can succeed individually while the parent correctly refuses reconciliation.

This is three GETs / 60 documented fixture weight. The fixture headers remain
synthetic samples; they do not measure total usage, renew rate freshness or establish
remaining quota. Metadata and each account retain their own original clocks and
rate evidence. Account responses do not gain inferred limits from the metadata.
The separate ordinary-process 20-operation / 16-GET / 448-weight collector and frozen
real 17-GET / 468-weight draft are unchanged.

The sequence verifies linked receipts from one root run and selected installation.
It does not establish an atomic account snapshot, user-stream fence, absence of
intervening changes, actual source authority, full account equity, or trade admission.
It uses public RFC 8032 test keys and four synthetic assets only. There are no open
order reads, same-run market route derivation or concurrent WebSocket transport yet.
No credentials, real venue requests, host installation, maintenance windows,
services, execution runners, upstream source or consumed real scopes were changed.

## Durable ordering and custody

`gateway_read_sequence.py` creates the exclusive root-owned
`fixture-read-sequence-v1` parent scope. Even a startup failure leaves it consumed;
a new process cannot resume, reset or create the same scope again.

Each fixed step has a distinct subdirectory and the existing one-attempt ledger,
request selection, kernel lifecycle, TLS original and native receipt. The parent
fsyncs preparation before starting the step. The child's installation binding
includes the exact parent preparation prefix and step index, so another run's
originals or a reordered duplicate cannot substitute for the selected step.

The root revokes the step's kernel mark before native response delivery. It closes
the one-step ledger before returning to the parent. The parent independently
replays the complete originals, requires the authenticated native acknowledgement,
successful attempt outcome and recorded revocation, checks original clock order,
and fsyncs acceptance before preparing another step. Trust, installation manifests,
network namespace, rules, route and frozen native runtime must remain consistent.
Completion requires all three accepted steps and a separate final record.

The parent retains no-follow descriptors for its directories, journal and immutable
child originals. It verifies inode/owner/mode, bytes and original authority before
subsequent work. Observed drift permanently ends that authority; restoring bytes
does not revive it. Persistence failure never creates a child step. Individual
kernel timeouts remain five seconds, signed request windows five seconds, TLS
operations four seconds and receipt delivery five seconds. There is no retry or
permission renewal; the three distinct requests each have their own single grant.

A controller killed between steps leaves accepted predecessors intact but no final
completion. A stopped last consumer is killed and reaped after the existing timeout;
its TLS may be complete while its native acknowledgement and parent acceptance stay
missing. Source drift after metadata prevents the next preparation. Replay does not
repair missing acknowledgements, refresh timestamps or infer current kernel state.
Power loss, rollback, malicious root races and broader runtime-library qualification
retain the prior implementation's limitations.

## Verification and diagnostic findings

**32 new / 794 focused tests pass**, without warnings, in 52.36 seconds.
The focused suite includes real native signatures and balance mapping through
credential-framed local channels, every parent prefix, cross-run/reordered originals,
rehashed parent/receipt tampering, missing acknowledgements, clock/order changes,
exact decimal equality, metadata mismatch, descriptor reuse, permanent drift refusal,
fsync failure and no-reopen behavior. Exact test source pins and captured output are recorded in the JSON.

Seven actual disposable sequence scenarios cover success, metadata precision mismatch,
second balance drift, second-read native rounding refusal, stopped consumer,
controller SIGKILL after the first account acceptance, and source drift after metadata.
Together with 26 legacy cases (seven signed account, seven native metadata,
seven native request custody and five echo), **33 current-source disposable scenarios
pass**. The unchanged pure TLS, stdlib receipt and IPC paths retain their earlier
namespace evidence and are covered by the focused Python regression.

Two fresh system-Python replays, with socket creation and DNS disabled, reproduce
all 33 selected original reports byte for byte. Two frozen-runtime native replays
also match: 28 scenario sets, 96 regenerated request envelopes, original currencies
and balances, and preserved precision refusals/missing acknowledgements. The seven
sequence cases contain 16 actual read steps and nine native signed account requests. Host observations remain unchanged; each scenario also
runs the base forty-check installation acceptance.

The first integration attempts exposed descriptor exhaustion before the first account
request: repeated ancestor opens in the parent's custody checks, combined with the
held 701-file native runtime, exceeded the inherited limit. The parent now reuses one
held descriptor per immutable path and directory. No system limit was increased,
and ownership/inode/content checks remain active. Actual acceptance records controller
descriptor counts during activation and native receipt delivery and checks they stay
below 1,024; the observed peak is **962 descriptors**. Failed diagnostic reports
remain unselected and are retained.

An early regression test harness also replaced the application's Python module
registry without restoring it. The new fixture now restores its original registry
on teardown; production isolated loading is unchanged. Development failures and
successful final verification are recorded separately in the JSON.

Selected originals live in `data/installed-read-sequence-2026-09-18/`. Ignored raw
reports, frozen runtime binaries, exact source copies and replay drivers are pinned
by the tracked JSON; earlier acceptance directories remain immutable.

Replay selected evidence without root or new capture:

```bash
/usr/bin/python3 -I data/installed-read-sequence-2026-09-18/replay.py
data/installed-read-sequence-2026-09-18/offline-runtime/bin/python3.12 -I -B data/installed-read-sequence-2026-09-18/native-replay.py
```

## Next implementation entrypoint

Extend this fixed sequence with open-order reconciliation and same-run book/metadata
route selection, then integrate concurrent gateway-owned TLS/WS for the complete
native collector. Preserve per-operation consumption, native acknowledgements and
original clocks. Real source/coverage/clock/charge qualification, host rollout,
full equity and UTC baselines, and trading remain blocked. Bootstrap, public-depth
and ADR-017 scopes remain consumed. No new ADR or long-running service is required.
