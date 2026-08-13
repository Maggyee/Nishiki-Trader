# 2026-08-13 Protocol v25 Provider Qualification

- **Status**: all-chain and Ethereum TVL qualified; Bitcoin TVL provider-rejected.
- **Pre-data commit**: `c69f579` on `origin/main`.
- **Signals/PnL**: unopened.
- **Trading effect**: none.

Each locked DefiLlama historical-chain-TVL URL was opened exactly once from the
freeze HEAD. All-chain and Ethereum current histories each contain 1,157
unfilled rows from 2019-11-01 through 2022-12-31: 61 warmup observations and
1,096 development observations with a one-calendar-day maximum gap. 1,321
later rows were counted and ignored; they were not written into the
development factors and were not used for signals or PnL. Snapshot and factor
hashes are recorded in the machine qualification artifact. TVL is a current
reconstruction, not a vintage tape.

Bitcoin-chain TVL failed the frozen coverage gate after its one GET: the
development reserve has only 652 observations versus 700 required. No snapshot
or factor was written, and retry is forbidden.

The two unchanged all-chain and Ethereum five-observation TVL-expansion
identities may now generate 2020-2022 signals and exactly two clean Nautilus
cash replays each. Bitcoin-chain TVL expansion cannot enter development. 2023-2025
values and PnL remain sealed. This qualification does not alter SourcePolicy,
existing paper shadow, testnet, live trading, or the future blind.
