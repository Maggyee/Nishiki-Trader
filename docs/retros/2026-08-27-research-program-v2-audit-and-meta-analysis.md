# Retro: Research Program v2 Audit, ADR-014, and First Meta-Analysis

- **Date**: 2026-08-27
- **Operator directive**: audit the current strategy program, explore along the
  five audit recommendations, and turn the process and its failure modes into
  agent-readable specification and warnings.
- **Artifacts landed**:
  - `docs/decisions/014-research-program-v2.md` (Accepted) — program rules v2.
  - `docs/research-program-warnings.md` — W1–W10 agent warnings (Always Read).
  - `docs/research-mechanism-backlog.md` — ranked orthogonal exploration axes B1–B8.
  - `docs/progress/research-mechanism-family-registry.json` +
    `apps/ops/research_family_registry.py` (`--check` enforced in tests).
  - `apps/ops/research_meta_analysis.py` +
    `docs/progress/research-program-meta-analysis-v1.{json,md}`.

## 1. What the first meta-analysis found (headline numbers)

Benchmark data: Binance Vision official monthly 1d klines, BTCUSDT,
2020-01..2025-12, 72/72 archives CHECKSUM-verified, 2192 rows, zero calendar
gaps (`data/meta/btcusdt-1d-closes-2020-2025.csv`,
sha256 `ad1dd81d4f6e174c…`). Only already-opened windows were read.

1. **The historical gate set is passable by beta alone.** Buy-and-hold at the
   standard 0.001 BTC trade size scores +71.03 USDT, 23/36 positive months,
   and 2/3 positive years on the 2023-2025 confirmation window — clearing the
   `>=18/36` monthly-breadth, `>=2/3` yearly, and positive-PnL gates with no
   strategy at all.
2. **No survivor beat buy-and-hold on its confirmation window.** Capture
   ratios vs B&H range from 19.3% (v46 premium) to 99.5% (v34 FVX). The best
   survivor matched holding; every other survivor returned less than holding.
   No survivor's monthly breadth is distinguishable from B&H months (all
   binomial p ≥ 0.575).
3. **The survivor count is consistent with luck.** Random long/flat timing
   with survivor-like exposure and holding cadence passes the two-stage
   (development + confirmation) historical gates 7.39% of the time. Across
   the registry's 108 PnL-opened identities, the expected number of lucky
   two-stage survivors is 7.98; we observed 10 (P(≥10 by luck) = 0.275).
4. **Pseudo-diversification is now measurable.** v18 and v40 (both VXN) carry
   identical confirmation rows (+60.21 USDT, 72 positions) — one trade held
   as two "independent" survivors.

## 2. Interpretation and decisions

- The ten `paper_shadow` survivors, taken together, currently demonstrate
  **beta timing indistinguishable from luck**, not alpha. Per ADR-014 §5.4
  this report demotes nothing by itself, but any future
  `paper_shadow → paper_simulated` review must confront these numbers
  (ADR-014 §6.2), and per §6.3 no current survivor qualifies for testnet
  effort on standalone evidence.
- The `external_index_relief` family is saturated (ADR-014 §3.3); protocols
  v49+ must declare an `open` family and orthogonality rationale before data
  access, enforced by `research_family_registry.py --check` in the test suite.
- Future protocols run under Gates v2 (ADR-014 §4): benchmark-relative base
  PnL, bootstrap p ≤ 0.10, ≥60 positions per window, deflated-expectation
  reporting, directional declaration, weekend-coverage statement.
- Exploration continues along `docs/research-mechanism-backlog.md`: B1
  multi-factor ML over the archived point-in-time panel is priority 1; B2
  funding-rate mechanisms and B3 cross-sectional relative value follow. All
  sealed protocols stay sealed; the 2026-09..2027-01 future blind stays sealed.

## 3. Boundaries honored

- No `SignalEvent` writes, no `SourcePolicy` changes, no collector changes,
  no order-path impact, no reopening or retuning of sealed protocols v2–v48.
- Benchmark data access was one-shot, official-archive, checksum-verified,
  limited to already-opened evaluation windows.

## 4. Environment note

This session ran on a Windows checkout. Eight collector test modules import
Unix-only `fcntl` and cannot collect on Windows
(`tests/ops/test_research_v{2,8,12,16,18,22,34,36}_*daily.py`); they are
unaffected by this change set and pass on the Linux data host. The remaining
suite plus the new tests pass locally.
