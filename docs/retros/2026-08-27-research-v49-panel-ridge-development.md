# Retro: Protocol v49 Multi-Factor Panel Ridge — Development Rejection

- **Date**: 2026-08-27
- **Identity**: `freqai_panel_ridge_v1 / panel17-ridge-mwf-oos2020h2-v1` (family `multifactor_ml`)
- **Outcome**: `development_rejected` under Gates v2 — **protocol closed, identity permanently dead, confirmation never opened.**
- **Evidence**: `docs/progress/phase-2-research-v49-provider-qualification.json`,
  `docs/progress/phase-2-research-v49-development-results.json`
  (contract `apps/ops/research_protocol_v49.py`, both stamped with the same `contract_sha256`).

## 1. What ran

First protocol executed under ADR-014 Gates v2, frozen at commit `be1250d`
before any factor value was opened. Qualification passed cleanly: all 34
pinned snapshot SHA256s matched, and the official Binance Vision closes CSV
(2019-12-01..2025-12-31, 2223 rows, 73/73 monthly archives CHECKSUM-verified)
covered the required range. Development then ran the frozen monthly-refit
expanding ridge walk-forward over the 2020-07..2022-12 OOS window for the
five-point alpha grid, selected α=10 by base net PnL as pre-registered, and
applied Gates v2 with two reproducible duplicate replays.

## 2. Result (selected α=10)

| Metric | Value | Gate | Verdict |
|---|---|---|---|
| Base net PnL | +11.99 USDT | > 0 | pass |
| Stress net PnL | +10.06 USDT | > 0 | pass |
| Positive months | 15/30 | ≥ 15 | pass (at the line) |
| Positive years | 2/3 | ≥ 2 | pass |
| Closed positions | 94 | ≥ 60 | pass |
| Benchmark-relative | +11.99 vs floor +4.14 (56.7% exposure × B&H +7.31) | above | pass |
| **Leave-best base PnL** | **−1.06 USDT** | > 0 | **fail** |
| **Bootstrap p-value** | **0.2197** | ≤ 0.10 | **fail** |

Alpha-grid base PnL: α=1 → −4.80, α=10 → +11.99, α=100 → −6.09,
α=1000 → +2.61, α=10000 → +5.54. The sign flips across neighboring grid
points are themselves evidence that the selected result is noise-fitting
rather than a stable conditional signal; the bootstrap gate priced that in.

## 3. Interpretation

The B1 hypothesis — that the *combination* of the archived point-in-time
factors carries next-day BTC information that no single factor carried — is
rejected at daily horizon under a linear (ridge) model: profits concentrate
in one position and the total is indistinguishable from random timing with
matched exposure (p = 0.22). This is also the first live demonstration that
Gates v2 rejects a candidate the legacy statistical intuition might have
promoted: six of eight gates passed, including beating the exposure-matched
buy-and-hold benchmark.

## 4. What is now closed vs. open

- Closed forever: this identity, its factor list, grid, and windows. No
  retuning, no grid extension, no ensemble, no gradient-boosting "variant"
  under this identity (contract §4 and warnings W2/W3).
- The `multifactor_ml` family stays `open`: a future study with a genuinely
  different pre-registered design (e.g., different horizon, nonlinear model
  class declared upfront, or an expanded panel including forward-collected
  data) requires a new protocol identity frozen before data access.
- Next backlog step per ADR-014 §7 fallback: **B2 funding-rate mechanisms**
  (`crypto_derivatives_structure`), which needs a new pre-registration.

## 5. Boundaries honored

Sealed protocols untouched (archived snapshots were read-only inputs);
2026-09..2027-01 future blind untouched (closes end 2025-12-31); no
`SignalEvent` writes; no `SourcePolicy` changes; no collector changes; the
ten `paper_shadow` survivors and their forward collection continue unchanged.

## 6. Process notes

- Freeze discipline held: pre-freeze host reads were limited to file hashes,
  headers, row counts, and date coverage; the freeze commit (`be1250d`) was
  pushed to origin before `develop` opened any factor value.
- The ADR-014 §5.5 meta-analysis rerun (registry PnL-opened count 108 → 109)
  is deferred: one additional trial moves the expected lucky-survivor count
  from 7.98 to ~8.06 and changes no conclusion. Rerun when a materially
  larger batch completes.
- This session ran from the Windows workstation via SSH to the research host;
  GitHub was unreachable from the workstation mid-session, so the freeze
  commit traveled by `git bundle` over SSH and was cherry-picked and pushed
  from the host — commit provenance is recorded in both messages.
