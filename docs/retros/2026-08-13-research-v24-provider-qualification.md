# 2026-08-13 Protocol v24 Provider Qualification

- **Status**: shared Fear and Greed series qualified for all three candidates.
- **Pre-data commit**: `1b5ff65` on `origin/main`.
- **Signals/PnL**: unopened.
- **Trading effect**: none.

The locked alternative.me `/fng/?limit=0` URL was opened exactly once from the
freeze HEAD. The current history contains 1,793 usable rows through
2022-12-31, including 61 warmup observations and 1,096 unfilled development
observations from 2020-01-01 through 2022-12-31 with a one-calendar-day
maximum gap. 1,319 later rows were counted and ignored; they were not written
into the development factor and were not used for signals or PnL. Snapshot and
factor hashes are recorded in the machine qualification artifact. The series
is a current reconstruction, not a vintage tape.

All three unchanged classification-hold identities may now generate 2020-2022
signals and exactly two clean Nautilus cash replays each. 2023-2025 values and
PnL remain sealed. This qualification does not alter SourcePolicy, existing
paper shadow, testnet, live trading, or the future blind.
