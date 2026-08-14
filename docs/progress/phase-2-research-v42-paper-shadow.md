# Phase 2 Alpha Research Protocol v42 Paper Shadow Specification (VIX6M Relief)

- **Status**: active paper shadow.
- **Strategy**: `rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1` (Cboe 6-Month Volatility Index Relief).
- **Execution Engine**: NautilusTrader netting cash simulator.
- **Signal Storage**: SQLite database at `data/research-v42/shadow/signals.db`.
- **Scheduled Cadence**: Mon–Fri 03:45 UTC.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.
