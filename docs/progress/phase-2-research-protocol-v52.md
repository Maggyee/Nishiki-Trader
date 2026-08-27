# Research Protocol v52 — Cross-Sectional Long/Short States (ADR-014 / backlog B3)

- **Status**: Pre-registered (frozen before any price value was opened for evaluation)
- **Date frozen**: 2026-08-27
- **Mechanism family**: `cross_sectional_relative` (open; first protocol-era member)
- **Identities**:
  - `rule_crypto_xs_momentum_ls_v1 / crypto-xs-mom30d-top3-bottom3-weekly-v1`
  - `rule_crypto_xs_reversal_ls_v1 / crypto-xs-rev7d-top3-bottom3-weekly-v1`
  - `rule_crypto_xs_lowvol_ls_v1 / crypto-xs-lowvol30d-top3-bottom3-weekly-v1`
- **Contract**: `apps/ops/research_protocol_v52.py` (`contract_sha256()` stamped
  into every stage output)
- **Pipeline**: `apps/ops/research_v52_xs.py`, a thin binding of the shared
  cross-sectional harness `apps/ops/research_xs_portfolio.py` (ADR-014 §6.4)
- **Gates**: Gates v2 mapped to the dollar-neutral portfolio class (see §4)

## 1. Hypothesis and orthogonality (ADR-014 §3.4)

First two-sided, multi-asset protocol in the program. Dollar-neutral
long/short rank portfolios remove the shared long-BTC beta by construction,
so the tested edge is pure *relative selection skill* — orthogonal to every
`paper_shadow` survivor and to all sealed single-asset timing rules. Three
different mechanisms share one frozen construction (no per-mechanism
parameter grids; lookbacks are standard literature constants):

| Candidate | Ranking (trailing) | Long | Short |
|---|---|---|---|
| `xs_mom_30d` | 30d simple return | top 3 | bottom 3 |
| `xs_rev_7d` | 7d simple return | bottom 3 | top 3 |
| `xs_lowvol_30d` | std of 30d daily returns | lowest 3 | highest 3 |

Non-duplication: the legacy 16-candidate era rejected four **long-only**
rotations; the market-neutral construction those rotations never had is
exactly what v52 tests. No sealed identity's condition or fingerprint is
reused.

Declarations: **two-sided (backtest only)** — short-leg funding/borrow drag
is not modeled (spot closes) and is recorded as a limitation for any later
review. Weekend coverage: all inputs 24/7 official archives; Monday 00:00
UTC close rebalances. Universe survivorship: full-coverage requirement
biases toward survivors; mitigated (not eliminated) by both legs drawing
from the same surviving pool; recorded as a limitation.

## 2. Frozen data contract

- Pool: 22 hand-listed USDT spot pairs listed on Binance on/before
  2019-10-01 (`SYMBOL_POOL`). Universe = pool members whose official monthly
  1d kline archives fully cover the development fetch range (2019-10..2022-12,
  CHECKSUM-verified, one GET per file); failures are excluded and logged,
  never substituted; minimum 12 survivors else the protocol blocks.
- **Staged fetch boundary**: confirmation months 2023-01..2025-12 may be
  fetched only after a development pass (enforced in `run_confirm`).
- **Delisting rule**: a symbol whose archive ends inside a window is
  force-closed at its last available close and excluded from rankings
  thereafter; no substitute enters. If the eligible universe falls below 12,
  the book goes flat until it recovers.

## 3. Frozen construction

k=3 legs per side, equal weight, 100 USDT fixed notional per leg (no
compounding), weekly Monday-close rebalance, signals from closes ≤ the
rebalance close, positions carried until the next rebalance. Costs per
entering and per exiting leg fill: gross/base/stress = 0 / 12 / 15 bps of
leg notional (side flips count as two fills).

## 4. Windows, gates, advance rule

Development 2020-01-01..2022-12-31 and confirmation 2023-01-01..2025-12-31
(both 36 months). Gates v2 mapping for the portfolio class: base/stress
net PnL > 0; ≥2/3 positive years; ≥18/36 positive months; **≥60 closed leg
positions**; leave-best (drop the single best leg episode) > 0;
benchmark-relative floor = net-exposure fraction × 100-USDT BTC buy-and-hold
(≈0 for a dollar-neutral book — the binding statistical test is the
permutation gate); **rank-permutation p ≤ 0.10** (20,000 trials, seed
20260827: identical calendar/universe/legs/costs, ranking replaced by an
independent uniform random permutation at every rebalance); two duplicate
replays. Among development passers only the highest base-PnL candidate opens
confirmation; the others record `development_passed_not_advanced`.
Development/confirmation failures close their identities permanently — no
retuning, lookback search, k search, or ensemble.

## 5. Boundaries

No `SignalEvent` writes, no `SourcePolicy` changes, no sealed-protocol
reopening, no future-blind access (data ends 2025-12-31), no live-path
impact. Stage outputs land in
`docs/progress/phase-2-research-v52-{provider-qualification,development-results,confirmation-results}.json`.
