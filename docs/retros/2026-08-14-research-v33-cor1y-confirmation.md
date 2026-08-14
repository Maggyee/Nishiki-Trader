# 2026-08-14 Protocol v33 COR1Y Confirmation Review

- **Status**: confirmation failed; protocol closed.
- **Candidate**: unchanged Cboe 1-Year Implied Correlation Relief (`cor1y_relief`).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed.
- **Trading effect**: none.

## Confirmation outcome

From confirmation freeze commit `843b52a`, the 2023-2025 factor series was extracted without new network access from the already-qualified snapshot `data/research-v33/raw/cor1y-20260814T013543Z-0cba3dd6341e.json` (752 observation days, 42 warmup rows, max calendar gap 4 days).

Two duplicate clean Nautilus cash replays were executed against the locked `data/research-v8/catalog` (BTCUSDT 1h, 2023-2025). The replays match 100% with identical fills (`sha256:ce1df3e5539b505f75a170c44515453f2050aff99af17a16b8aa4175b7d31433`), zero short positions, zero effective blockers, and zero events in verified no-kline hours.

| Metric | Required | Observed | Gate |
|---|---|---|---|
| Base net PnL | > 0 | +70.993537 USDT | PASS |
| Stress net PnL | > 0 | +70.962283 USDT | PASS |
| Positive years | >= 2 / 3 | 1 / 3 (2023: -0.003, 2024: 0.0, 2025: +71.00) | **FAIL** |
| Positive months | >= 18 / 36 | 1 / 36 | **FAIL** |
| Closed positions | >= 30 | 1 | **FAIL** |
| Leave-best base net PnL | > 0 | 0.000000 USDT | **FAIL** |
| Duplicate replays | 2 | 2 (identical fills) | PASS |
| Evidence blockers | 0 | 0 | PASS |

While `cor1y_relief` produced positive net PnL in 2025 (+70.99 USDT base), signal density collapsed during 2023-2025 (only 7 signals and 1 closed trade across 36 months). It severely fails activity (1 < 30 positions), year breadth (1 < 2 years), monthly breadth (1 < 18 months), and concentration (leave-best is 0.0).

`cor1y_relief` resolves to `reject_candidate`. Protocol v33 is closed. No candidate from Protocol v33 advances to `paper_shadow` dry-run. The future blind remains sealed.
