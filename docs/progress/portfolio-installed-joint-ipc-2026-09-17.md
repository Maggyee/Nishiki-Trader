# Installed dedicated UID exchanges durable multi-operation accounting receipts

Date: 2026-09-17. Disposable namespaces and local IPC only; zero venue requests.

The installed fixture now supports a bounded 20-operation IPC sequence between
its dedicated UID child and the root-owned attempt ledger. Every request and
receipt is checked using kernel-supplied PID/UID/GID credentials. Root persists
the selected operation before sending a preparation receipt; the child confirms
receipt before the next operation can be consumed.

This completes the multi-operation **IPC/accounting boundary**. It does not yet
connect the ordinary-process native joint collector to the root TLS transport.
The child requests fixed classification tokens, not signed account payloads,
route selectors or market subscriptions. An IPC confirmation is not a transport
outcome, provider usage observation, capacity reservation or dispatch permit.
The fixture never grants an egress mark; kernel tests reject marked sockets even
after a successful 20-operation session. The existing one-GET TLS fixture remains
a separate mode.

## Protected installation and fixed accounting scope

`gateway_joint_ipc.py` reuses the original pinned launcher's `ControlChannel`,
SOCK_SEQPACKET framing, per-message `SCM_CREDENTIALS` checks, pidfd, capability
drop and isolated network namespace. It does not replace the base installation
bundle or introduce a listening socket/service. The supplemental fixture manifest
is now **v3 / eight protected sources**. The base installer remains pinned to
bundle SHA256 `995380e089df6c658a2ee7fa8224441d6173ed08b9656fc6447fad85d62800ec`.
Old source snapshots and consumed scopes remain unchanged.

The extension is executed only after the fixed installed path, isolated Python,
root identity, namespace context and held source descriptors pass verification.
The child executes only the held base launcher and held extension plus the fixed
token inventory. It has no root file descriptors, capabilities, supplementary
groups or IP route to the fixture peer. Same-UID siblings cannot impersonate its
PID; cached socketpair peer credentials do not substitute for message credentials.

A distinct ledger profile, `portfolio.fixture_joint_ipc_ledger.v1`, consumes
`/var/lib/trader/egress/fixture-joint-ipc-v1`. It requires the exact request packet
hash, index, caller classification and operation at every preparation. Outcomes
must reference the same request. The old one-GET and ordinary joint profiles
retain their original schemas, directories and explicit replay selection.

The fixed maximum local-pilot sequence classifies **16 GETs, three account API
operations and one market connection**: **448 documented weight**, two WS
connection preparations and one unresolved market charge. Depth slots are only
three classification positions; this fixture does not choose or authenticate
symbols. Unit acceptance derives the same class order from the existing native
collector's request budget. Before each operation, root recomputes consumed plus
remaining units from its own fixed schedule; callers cannot supply cheaper
weights or omit failed consumption. These are a fixture envelope, not current
provider limits or headroom. The frozen real draft remains 17 GETs / 468 weight.

## Failure and receipt ordering

Canonical bounded messages contain exactly version, operation token and sequence.
Extra endpoint/payload fields, order methods, wrong/repeated/skipped sequence,
oversize packets and descriptor passing are rejected by the reused channel.
The original channel closes received descriptors before rejecting them.
Only a successful preparation fsync and fresh binding/deadline checks allow the
root `prepared` receipt. Only the matching authenticated `received` reply allows
a successful local outcome. The next request cannot advance a pending operation.

The protocol has a 30-second session deadline, five-second receive bounds and
bounded archives. Checks occur before and after blocking/persistence boundaries;
synchronous filesystem work is not preemptible. Failure closes IPC and reaps the
child, retaining prior consumption and a pending operation where applicable.
A failed preparation fsync may leave no accepted row, but its scope remains
consumed and the child receives no success receipt. A failed outcome fsync blocks
the next operation. SIGKILL after the tenth durable preparation leaves index 9
pending; channel loss causes the orphan child to exit and the namespace parent
reaps it. No request, retry or scope reconstruction follows restart.

A completed ledger records successful IPC confirmations only. Offline reports
explicitly keep `transport_dispatch_verified`, `provider_usage_inferred`,
`caller_labels_authenticated`, complete coverage and real admission false.
Source hashes and selected history cannot reconstruct the held runtime authority.
The new CLI selector only reviews original records:

```bash
uv run python -m apps.ops.portfolio_egress_ledger --ipc-profile \
  --archive ATTEMPTS.jsonl --archive-sha256 ORIGINAL_SHA256 \
  --binding-sha256 ORIGINAL_BINDING_SHA256 --report NEW-REPORT.json
```

Exit code 2 means a report was written with network admission blocked. The
existing `--joint-profile` selects the separate ordinary-process joint ledger.
Neither CLI loads credentials, starts a capture or opens a network connection.

## Actual acceptance and remaining integration

**28 new / 790 distinct focused tests pass**: the 788-test regression batch plus
two final CLI checks. Three existing fork deprecation warnings remain. Tests
cover fsync/acknowledgement ordering, packet/descriptor rejection, rehashed
request substitution, envelope equivalence, deadline loss and consumed-scope
refusal.

Six actual installed IPC scenarios pass, each reusing the base installation
acceptance and 48 checks (49 for controller crash):

| Scenario | Recorded operations | Pending index | Result |
|---|---:|---:|---|
| Success | 20 | null | Closed IPC ledger |
| Child SIGKILL | 10 | 9 | Binding refusal; prior consumption retained |
| Installed source drift | 10 | 9 | Permanent binding refusal |
| Account/group drift | 10 | 9 | Permanent binding refusal |
| Storage-mode drift | 10 | 9 | Unsealed original prefix retained |
| Controller SIGKILL | 10 | 9 | No synthetic outcome; child exits on EOF |

Every scenario checks dedicated-UID code/state access refusals, no privileged
file descriptor inheritance, an empty permission set, actual marked-socket
kernel denial, fresh-process scope refusal and the unchanged original consumed
sentinel. Selected host observations and caller namespaces match before/after.
All **six TLS and five echo regressions** also pass under the v3 inventory.
Two fresh isolated system-Python processes reproduce all **17** sets of original
attempt/kernel/TLS reports from retained source copies without network access.

The [result JSON](portfolio-installed-joint-ipc-2026-09-17.json) pins those reports,
sources, replay driver and exact Python-test results. Retained originals are in
`data/installed-joint-ipc-2026-09-17/`; the earlier initial IPC capture is unselected.
No private fixture key is exported. Full unrelated application regression was
not rerun. No host installation, maintenance window, upstream source, service,
SignalEvent, SourcePolicy, execution runner or live order path changed.

Next connect the actual native collector's request/receipt flow to this installed
boundary and gateway-owned TLS sockets, including signed account selectors,
same-run route validation, original receipt clocks, WS control frames and the
expiring kernel lifecycle. Fixed IPC tokens alone do not validate those bytes.
Real authorities, all-caller history, unknown provider charges and rate/clock
qualification remain blocked. Consumed bootstrap/ADR-017/depth scopes stay
consumed; strict continuity is 0/14 and live trading remains blocked.
