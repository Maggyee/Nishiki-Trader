# Phase 2 Research Protocol v13

- **Frozen**: 2026-08-12 before opening the Coin Metrics time-series body.
- **Status**: development complete; zero confirmation-eligible candidates.
- **Trading effect**: none.

V13 locks three BTC on-chain mechanisms: active-address 7/30 expansion,
positive-value transfer-count 7/30 expansion, and MVRV distress below the
structural value of one. They represent participation, settlement activity,
and market value relative to realized aggregate cost basis respectively.

The exact Community API request and all rules are frozen together. Daily
observations for UTC day D are consumed only at D+2 00:00 UTC. Present-day
history is treated as finalized-ledger reconstruction evidence, not as a claim
that the provider response existed unchanged historically. Missing rows are
never filled.

The 2020-2022 development reserve opens once after qualification. Every
candidate must pass cost, three-year/month breadth, 30-position activity,
leave-best concentration, long/flat lineage, verified Binance downtime, and
duplicate replay gates before its 2023-2025 confirmation may open. V12 stablecoin
forward collection, GVZ paper shadow, and the shared future blind are separate
and unchanged.

## Development outcome

The one allowed response contained all 1,157 daily rows from 2019-11-01
through 2022-12-31 for all three metrics. Its immutable snapshot hash is
`sha256:2af15212f18f210c10c5a6f0814cc1fe7eb724b32b03457c50ddddff5a4aa016`.
No missing row was filled.

| Candidate | Signals | Base / stress PnL | Positive years / months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---|
| Active-address expansion | 100 | +6.915612 / +5.979135 | 2/3 / 15/36 | 50 | -5.677340 | reject |
| Transfer-count expansion | 120 | -15.162113 / -16.235711 | 1/3 / 12/36 | 60 | -28.502804 | reject |
| MVRV below one | 13 | +1.918861 / +1.848863 | 2/3 / 4/36 | 7 | -0.699503 | insufficient evidence |

All duplicate replay pairs reproduce exactly, remain Spot long/flat, have no
effective evidence blockers, and place no event in an independently verified
Binance no-kline hour. Active-address expansion is cost-positive but fails
monthly breadth and concentration. Transfer-count expansion is negative.
MVRV distress is cost-positive but too sparse and concentrated to establish an
edge; it is retained only as a research lead. The 2023-2025 confirmation and
future blind remain sealed.
