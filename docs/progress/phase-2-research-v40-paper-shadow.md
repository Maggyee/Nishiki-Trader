# Phase 2 Alpha Research Protocol v40 Paper Shadow Specification (VXN NASDAQ Volatility Relief Expansion)

- **Strategy**: `rule_cboe_vxn_relief_v1 / cboe-vxn-diff5-negative-lag1d-v1` (Cboe NASDAQ Volatility Index Relief).
- **Status**: active paper shadow.
- **Cadence**: Weekdays at 03:00 UTC (`0 3 * * 1-5`).
- **Goal**: Collect forward out-of-sample point-in-time daily index values, audit drift, emit `SignalEvent v1` into `data/research-v40/shadow/signals.db`, and record health status in `docs/progress/phase-2-research-v40-paper-shadow-status.json`.
- **Trading effect**: None; forward research signals only; live trading remains blocked by the Phase 6 gate.
