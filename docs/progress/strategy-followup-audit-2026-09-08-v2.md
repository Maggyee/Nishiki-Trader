# Operator-confirmed budget audit — 2026-09-08 v2

The operator explicitly confirmed **100 USDT planned capital / 50% maximum
drawdown preference / 50 USDT daily loss budget**. The read-only evaluator now
uses these inputs exactly; it does not substitute 5 USDT or require another
confirmation. See the [v2 method](strategy-followup-method-2026-09-08-v2.md) and
matching JSON. All old reports and frozen research evidence remain unchanged.

## Results

On the same six hash-verified 2023–2025 candidates, neither the raw fixed-size
basket nor its previously defined duplicate-normalized diagnostic has a daily
sampled loss reaching 50 USDT under gross/base/stress accounting. This replaces
only the old report's 5 USDT breach counts; it is not intraday-loss assurance.

The base-cost duplicate-normalized diagnostic still requires at least **308.85
USDT** cash at daily marks, has **80.21 USDT** maximum marked drawdown, and
**22.61 USDT** worst sampled daily loss. Thus the 50 USDT daily comparison is
not breached, but the 100 USDT funding budget and static 50 USDT total-drawdown
budget remain insufficient. No executable weights or leveraged workaround were
selected. These are not actual results from a funded 100 USDT account.

The four missing original evidence chains (including dirty v42 manifests),
elapsed forward-observation requirement, and missing verified account equity
remain unresolved. The user's research-budget choice itself is now resolved.

## Scope and verification

- Changed `apps/ops/research_strategy_followup.py`: exact diagnostic input, v2
  schema/method, separate unchanged runtime-rule reference. No runtime setting,
  SourcePolicy, collector cadence or trading permission changed.
- Updated `tests/ops/test_research_strategy_followup.py`: 20 targeted tests pass,
  including exact 5/10/50 USDT input and inclusive threshold comparisons.
- Added versioned method/report JSON/Markdown; updated `docs/project-status.md`
  and `docs/agent-reading-list.md`. Old v1 evidence was not overwritten.
- Ruff and registry check passed; real v2 evaluation returned the expected
  partial status due to evidence/time/funding constraints, not budget approval.
- Full offline suite: 1,699 passed, 12 Postgres integration tests deselected
  (no dedicated DSN supplied). Original v1 method/report bytes match Git exactly.
- No upstream source touched; no effect on the live trading path. Existing
  execution settings are outside this research-budget change.
