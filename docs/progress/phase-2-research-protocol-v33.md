# Phase 2 Research Protocol v33

- **Status**: pre-registered before Cboe correlation term structure body access.
- **Mechanisms**: Cboe Implied Correlation Term Structure relief (COR3M, COR6M, COR1Y).
- **Development**: 2020-01-01 through 2022-12-31; unopened.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

Protocol v22 tested `COR1M` (1-month implied correlation) along with tail skew (`SKEW`) and dispersion (`DSPX`). COR1M measures very short-term index vs constituent option co-movement (heavily influenced by 30-day index option dynamics).

Protocol v33 investigates the **term structure of implied correlation**:
1. `COR3M`: 3-month implied correlation (quarterly horizon, aligning with corporate earnings cycle and standard institutional hedging horizon);
2. `COR6M`: 6-month implied correlation (semi-annual horizon);
3. `COR1Y`: 1-year implied correlation (structural annual horizon across top 50 S&P 500 equities).

These represent independent macro risk mechanisms: structural and multi-month equity co-movement can ease even when short-term correlation spikes, or vice-versa. Falling medium-to-long term implied correlation indicates market participants expect systemic clustering to dissipate and idiosyncratic diversification to return, a classic macro risk-on regime favorable to crypto asset expansion.

Each rule buys BTCUSDT Spot only when the latest completed official close minus the close five official observations earlier is strictly negative; otherwise it is flat. There is no sign flip, lookback grid, ensemble, or post-result reparameterization.

Official Cboe historical-data documentation was opened. No `*_History.csv` body, close value, signal, or PnL is opened until this contract is committed and pushed. Each index may be fetched once. Decisions wait one calendar day after the official DATE. Factors use only warmup plus 2020-2022 rows even if the CSV continues later. There is no historical-vintage claim.

Development replays must use the already-audited 2020-2022 downtime catalog (`data/research-v7-downtime-sensitivity/catalog`). Confirmation, if later frozen separately, uses the v8 catalog (`data/research-v8/catalog`). Existing paper-shadow collectors, SourcePolicy, testnet, live trading, and the shared future blind stay untouched.

## Gates and progression

Unchanged development gates:
- Base net PnL > 0.0 USDT
- Stress net PnL > 0.0 USDT
- Positive calendar years >= 2/3
- Positive calendar months >= 18/36
- Closed positions >= 30
- Leave-best-position-out base net PnL > 0.0 USDT
- Duplicate clean-git replays = 2

A development passer may only enter a separately frozen 2023-2025 confirmation contract. A confirmed passer may only become eligible for a separate ADR-007 `paper_shadow` review.
