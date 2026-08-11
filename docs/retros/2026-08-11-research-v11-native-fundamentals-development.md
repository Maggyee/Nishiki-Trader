# 2026-08-11 Protocol v11 Native-Fundamentals Development Review

- **Status**: complete; two candidates rejected and one is insufficient evidence.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed and not opened.
- **Future blind**: sealed and not opened.
- **Trading effect**: none.

## Data decision

Protocol v10 first opened the three exact Coin Metrics Community API requests
from clean commit `4b68e64`. All routes had complete coverage, but none of the
4,628 rows carried provider status-time metadata, so v10 closed without factor
values, signals, or PnL.

Protocol v11 was then committed at `dd70348` before factor values or PnL were
opened. It preserves the three rules and raw response hashes, interprets each
daily metric as a canonical finalized-ledger reconstruction, and delays every
observation until D+2 00:00 UTC. It does not claim a historical provider
vintage. This permits a replication test, but any historical survivor would
still require forward immutable snapshots before paper_shadow.

## Results

| Candidate | Signals | Gross PnL | Base PnL | Stress PnL | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Hashrate 7/30 recovery | 114 | +6.552360 | +2.805893 | +1.869277 | 2/3 | 14/36 | 57 | -23.170591 | reject |
| USDT+USDC 30-observation expansion | 13 | +23.303860 | +23.014887 | +22.942644 | 2/3 | 2/36 | 7 | -6.712348 | insufficient evidence |
| BTC fees 7/30 demand | 65 | +0.084290 | -2.384972 | -3.002288 | 2/3 | 14/36 | 33 | -14.656351 | reject |

Every candidate was replayed twice. Each duplicate pair has the same fills
hash, all paths remain Spot long/flat, all effective bundle blockers are empty,
and no order or fill lands in the 30 hours already verified as absent from both
the official Binance monthly archives and REST API.

## Interpretation

Hashrate recovery survives modeled costs but is not stable. It earns
`+8.739129/+25.684199/-31.617434` USDT in 2020/2021/2022, has only 14 positive
months, and becomes deeply negative after removing its best position. This is
a concentrated 2020-2021 effect, not a robust three-year edge.

Stablecoin expansion has the strongest headline return, but the rule changes
state only 13 times and closes seven positions. Only two calendar months
contain positive realized base PnL, and removing the best position changes the
result to `-6.712348` USDT. It is therefore classified as insufficient
evidence, not as a negative strategy result. The correct next evidence is a
forward immutable series under the unchanged rule, not shorter lookbacks or a
threshold search.

BTC fee demand is almost flat before costs and negative after costs. It also
fails monthly breadth and concentration despite meeting the 30-position
activity floor. Its positive 2020/2021 results reverse in 2022, so the long-on-
rising-fees sign is rejected under this identity.

## Decision

Protocol v11 has zero development passers. Do not open 2023-2025 confirmation,
retune the 7/30 or 30-observation lookbacks, reverse a sign, combine the three
signals after seeing PnL, or feed any v11 source into paper/testnet. Preserve
the stablecoin result as an undersampled research lead. The GVZ paper-shadow
process and shared future blind remain unchanged.

Machine detail is in
`docs/progress/phase-2-research-v11-development-results.json`.
