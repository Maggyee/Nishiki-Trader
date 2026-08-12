# 2026-08-12 Protocol v13 Network-Mechanisms Development Review

- **Status**: complete; two candidates rejected and one is insufficient evidence.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed and not opened.
- **Future blind**: sealed and not opened.
- **Trading effect**: none.

## Data decision

Protocol v13 was pushed before the one allowed Coin Metrics time-series body
was opened. The response has a complete 1,157-day grid for `AdrActCnt`,
`TxTfrCnt`, and `CapMVRVCur`; no row was filled. The immutable snapshot hash is
`sha256:2af15212f18f210c10c5a6f0814cc1fe7eb724b32b03457c50ddddff5a4aa016`.
Each observation for UTC day D is treated as a finalized-ledger reconstruction
available at D+2, not as a claim of provider-vintage history.

## Results

| Candidate | Signals | Gross PnL | Base PnL | Stress PnL | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Active-address 7/30 expansion | 100 | +10.661520 | +6.915612 | +5.979135 | 2/3 | 15/36 | 50 | -5.677340 | reject |
| Transfer-count 7/30 expansion | 120 | -10.867720 | -15.162113 | -16.235711 | 1/3 | 12/36 | 60 | -28.502804 | reject |
| MVRV below one | 13 | +2.198850 | +1.918861 | +1.848863 | 2/3 | 4/36 | 7 | -0.699503 | insufficient evidence |

Every candidate was replayed twice. Each pair has identical fills, zero short
positions, no effective blockers, and no order or fill in the 30 hours already
verified absent from both official Binance archives and REST.

## Interpretation

Active-address expansion survives modeled costs but is concentrated in
2020-2021. Its 2020/2021/2022 base results are
`+8.216512/+21.085528/-22.386427` USDT; only 15 months are positive, and
removing its best position makes PnL negative. This identity is rejected.

Transfer-count expansion loses before and after costs, has only one positive
year, and fails breadth and concentration. The hypothesis that a rising count
of positive-value transfers is directly bullish is rejected under this rule.

MVRV below one produces positive cost-adjusted PnL, but it changes state only
13 times and closes seven positions. Four months contain positive realized
PnL, and removing the best position makes the result negative. This is
insufficient evidence rather than a negative-return result. Its defensible next
evidence would be an unchanged, prospectively collected rule—not a tuned MVRV
threshold or an early opening of the sealed confirmation period.

## Decision

Protocol v13 has zero development passers. Do not open 2023-2025 confirmation,
retune either 7/30 rule, change the MVRV threshold, reverse signs, or construct
a PnL-selected ensemble. V12 stablecoin forward collection, GVZ paper shadow,
all SourcePolicy records, testnet, and live trading remain unchanged.

Machine-readable detail is in
`docs/progress/phase-2-research-v13-development-results.json`.
