# Fixed-session operator status and unknown-order handling — 2026-09-12

`apps.ops.portfolio_session_run --status` now inspects the fixed private session
without reading credentials, creating a lease, querying the exchange or writing
session state. This remains useful after an interrupted attempt, invalid credentials
or expiry of the collector's 24-hour history window. It is not a recovery command.

The summary reports original client order IDs and sides, last recorded status,
consumed submit/cancel intentions, durable dispatch records, recorded session-owned
BTC, halt history, checkpoint hash/time, record age, deadline and history expiry.
Prepared cancellation remains consumed even without a dispatch receipt. A recorded
attempt does not prove that a request reached the venue or received acknowledgement.

Missing/corrupt/inconsistent files, changed files during reading and a regressing
clock produce unknown state with null orders/ownership. No missing value becomes
zero or a fresh allowance. Root/file ownership, permissions, symlink refusal,
checkpoint policy, original IDs and activation/source consistency are checked.
The status reader takes no writer lock; stable repeated reads describe selected
local bytes, not the absence of an active process or a current venue state.

Successful matching/recovery reports now include the same operator summary with
`signed_reconciliation_at_observation` and the original receipt time. Failure
artifacts include a best-effort **local** summary. Summary failures remain unknown;
they do not replace the original runtime error or create a new admission decision.
The CLI's sanitized error output points to `--status` and the dedicated runbook.
No raw exception text, Key, signed URL or unrelated asset balance is added to stdout.

The collector and status helper share one `HISTORY_NS` constant; the value and
collector behavior are unchanged. Every summary states that it does not verify
current venue state, authorize a new order or permit a cancellation retry. A
successful signed terminal report recommends preserving its evidence and residual.
An expired local history window points to archived-evidence review, not repeated
GETs, changing timestamps or resetting the scope.

## Operation and actual local inspection

See [the fixed-session recovery runbook](../runbook-testnet-session-recovery.md)
for the state/action table, distinctions between preparation/dispatch/acknowledgement,
GET-only recovery, the narrowly guarded cancellation operation, unknown outcomes,
fee halts, missing files and history expiry. The main runbook now points this fixed
scope to that procedure instead of generic account-wide flatten/restart commands.

The actual `--status` invocation on September 12 read the completed original session:
`recorded_terminal_no_inventory`, original BUY CANCELED, two recorded dispatches,
consumed BUY/cancel opportunities, zero recorded owned BTC and expired history/deadline.
It performed no exchange observation. The original private checkpoint remained at
SHA256 `08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f`.
No new BUY, SELL or cancellation was attempted.

## Files and verification

- `apps/ops/portfolio_session_status.py`: read-only summaries and fixed-file checks.
- `apps/ops/portfolio_session_run.py`: local status mode, success/failure summaries and guidance.
- `apps/strategies_nautilus/portfolio_session_transport.py`: name the existing history constant.
- `tests/ops/test_portfolio_session_status.py` and `test_portfolio_session_run.py`:
  native empty/prepared/submitted/active/PendingCancel/terminal records, consumed
  cancellation without dispatch, history boundaries, corruption/unstable reads,
  sanitized failures and full CLI/report integration.
- Application READMEs, reading index, project status, main/dedicated runbooks and this report.

The 31 focused tests pass, including 18 new operator-status tests. Status CLI tests
forbid credential, git, lease and transport construction and preserve all private
fixture files. Full native fixture success/fee-failure reports retain the correct
evidence basis and ownership. No upstream source, order-admission/execution policy,
SourcePolicy, dependency, service, schedule or production path changed.

Final full offline regression: **2,621 passed, 12 deselected** in 179.54 seconds.
The 12 Postgres integration tests require an unavailable dedicated DSN. Ruff,
research registry and whitespace checks pass.

Next qualify offline replay of retained private session response archives, including
expired collector windows, while keeping historical evidence separate from fresh
source confirmation. Actual active recovery/fills/fees/cleanup and full-account
portfolio qualification remain unverified; the completed fixed scope stays consumed.
