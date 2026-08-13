# 2026-08-13 Protocol v22 Provider Qualification

- **Status**: SKEW and COR1M qualified; DSPX rejected at provider validation.
- **Pre-data commit**: `ee4bbe3` on `origin/main`.
- **Signals/PnL**: unopened.
- **Trading effect**: none.

Each pre-registered Cboe history URL was opened exactly once. SKEW returned the
locked scalar schema and COR1M returned the locked OHLC schema. Both provide
756 unfilled development observations from 2020-01-02 through 2022-12-30, 41
warmup observations, and a maximum four-calendar-day gap. Their immutable
snapshot and factor hashes are recorded in the machine qualification artifact.

DSPX returned a body but contains at least one non-positive value, violating
the frozen value contract. Validation stopped before a snapshot or factor was
written. The identity is provider-rejected without a retry or PnL.

Only unchanged SKEW relief and COR1M relief may now generate 2020-2022 signals
and exactly two clean Nautilus replays each. Their 2023-2025 values and PnL
remain sealed. This qualification does not alter SourcePolicy, paper shadow,
testnet, live trading, or the future blind.
