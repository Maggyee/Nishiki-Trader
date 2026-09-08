# Operator-confirmed diagnostic budget — 2026-09-08 v2

Status: accepted for research/portfolio diagnostics by the operator's explicit
follow-up, "按我给的来", after the prior 5 USDT substitution was explained.

The confirmed inputs are **100 USDT planned initial capital**, **50% maximum
drawdown preference**, and **50 USDT daily loss budget**. Use these exact inputs
in the read-only budget comparison. Do not clamp 50 USDT to 5 USDT and do not
continue asking the operator to reconfirm the same choice.

This supersedes only the budget-comparison section of the
[v1 method](strategy-followup-method-2026-09-08.md). Its evidence inventory,
fixed historical search tip, six-candidate verified cohort, 2023–2025 window,
costs, unchanged diagnostic weights, cash accounting, daily sampling and
prospective-integrity checks remain unchanged. The static total drawdown budget
is 50% of planned initial capital, or 50 USDT, not an actual peak-equity metric.

The v2 schema uses the exact input for daily-loss comparisons and labels the
budget source `operator_input`. It records the existing 5% execution-rule
reference separately, not as a clamp or unresolved research-budget choice.
Old v1 JSON/Markdown reports and their method remain immutable; append v2 outputs.

Scope is the current research budget assessment, not a command to enter live
trading, alter Nautilus runtime settings, change SourcePolicy, resize positions,
relax phase gates, or amend the global ADR-001 execution policy. No runtime
configuration is changed. Missing original evidence, elapsed forward time,
verified account equity and insufficient cash for the fixed-size basket remain
independent limitations. Raising the daily comparison amount cannot make an
otherwise unfundable basket executable.
