# 2026-08-13 Protocol v27 Provider Qualification

- **Status**: all three all-chain fee/revenue series qualified.
- **Pre-data commit**: `fd565b4` on `origin/main`.
- **Signals/PnL**: unopened.
- **Trading effect**: none.

Each locked DefiLlama `overview/fees` URL was opened exactly once from the
freeze HEAD. The three current histories (`dailyFees`, `dailyRevenue`,
`dailyHoldersRevenue`) each contain 1,157 unfilled rows from 2019-11-01
through 2022-12-31: 61 warmup observations and 1,096 development observations
with a one-calendar-day maximum gap. 1,321 later rows were counted and
ignored; they were not written into the development factors and were not used
for signals or PnL. Snapshot and factor hashes are recorded in the machine
qualification artifact. Fees are a current reconstruction, not a vintage tape.

The three unchanged five-observation cashflow-expansion identities may now
generate 2020-2022 signals and exactly two clean Nautilus cash replays each.
2023-2025 values and PnL remain sealed. This qualification does not alter
SourcePolicy, existing paper shadow, testnet, live trading, or the future
blind.
