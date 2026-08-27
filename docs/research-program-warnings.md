# Research Program Warnings

- **Status**: Active — **Always Read** before any research, gating, review, or promotion task.
- **Owner**: nishiki
- **Source**: 2026-08-27 program audit of protocols v2–v48 (ADR-014 §1 holds the evidence).
- **Update rule**: when a new audit finding becomes durable, add a numbered warning here (never delete; strike through with rationale if obsoleted). Do not restate these in `AGENTS.md`/`CLAUDE.md`.

Each warning: what happened → why it is a trap → what you MUST / MUST NOT do.

---

## W1 — Absolute-PnL gates in a rising market measure beta, not alpha

BTC rose over both evaluation windows (2020-2022, 2023-2025). A long/flat rule
with ~50% exposure passes "base_net_pnl > 0, 2/3 positive years" by holding
beta part-time. Ten survivors passed exactly such gates.

- MUST: for any long/flat candidate, compare `base_net_pnl` against
  `time_in_market_fraction × same-window buy-and-hold PnL` (Gates v2,
  ADR-014 §4) and against the random-timing Monte Carlo null
  (`apps/ops/research_meta_analysis.py`).
- MUST NOT: describe a positive absolute PnL as "alpha" in any retro, review,
  or status update without the benchmark-relative number beside it.

## W2 — Pseudo-diversification: same trade, many names

V18 (`cboe-vxn-ohlc5obs-negative-1d-v1`) and V40 (`cboe-vxn-diff5-negative-lag1d-v1`)
are the SAME index under two near-identical rules, both held as "independent"
survivors. All ten survivors express one position: long BTC in calm regimes.

- MUST: before proposing any candidate, look it up in
  `docs/progress/research-mechanism-family-registry.json`; if its family is
  `saturated`, reject at pre-registration (no data access).
- MUST: state in the pre-registration what world-state the new mechanism
  profits from that the current survivor set does not.
- MUST NOT: count low signal-panel correlation as diversification when the
  conditional position is identical (long BTC when externally calm).

## W3 — Per-protocol rigor does not fix program-level multiple testing

~47 protocols, >100 identities, mostly one family, screened by gates a lucky
long-only rule can pass. Individually clean protocols still produce lucky
survivors in aggregate.

- MUST: cite the registry totals and the latest meta-analysis lucky-survivor
  expectation (`docs/progress/research-program-meta-analysis-v1.md`) in every
  confirmation review.
- MUST: update the family registry in the same commit that freezes a new
  protocol (the `--check` gate fails otherwise).
- MUST NOT: treat "passed frozen gates" as sufficient evidence of alpha; the
  null hypothesis includes the whole program's search history.

## W4 — Tens-of-USDT PnL over 3 years is weak evidence, whatever the gates say

Survivor confirmation PnLs are +8.9 to +70.7 USDT at 0.001 BTC over 3 years
with as few as 72 positions. No t-stat or bootstrap gate existed before
Gates v2. `leave-best` alone is a coarse concentration check.

- MUST: apply the Gates v2 bootstrap p-value (≤ 0.10) and the ≥ 60
  positions-per-window floor to every new protocol.
- MUST NOT: argue statistical significance from breadth counts alone
  (18/36 months can be typical of buy-and-hold in the same window — check the
  meta-analysis B&H breadth numbers first).

## W5 — The 7-day forward shadow is a pipeline check, not performance evidence

The 7-day / 50-signal forward collection gate verifies schema stability,
freshness, and lineage. A daily-horizon rule emits ~5–10 signals in that
window; it has zero statistical power on returns.

- MUST: cite forward-shadow completion only as data-integrity evidence.
- MUST NOT: cite it as performance/alpha evidence in any promotion review, and
  MUST NOT propose `paper_simulated` on forward-shadow PnL alone.

## W6 — US-calendar external data vs 24/7 BTC is a structural mismatch

Cboe/FRED-style sources publish weekdays with 1–2 day lags and no historical
vintages. Weekend/holiday signal vacuum is mechanism-level; vintage risk is
mitigated (lag), not eliminated. Providers also repeatedly blocked or changed
formats mid-protocol (v17, v21, v28, v31, v32).

- MUST: include the Gates v2 `weekend_coverage_statement` in new contracts and
  prefer official immutable 24/7 archives (Binance Vision klines, premium
  index, funding) where the mechanism allows.
- MUST NOT: silently forward-fill weekend gaps or claim point-in-time fidelity
  for a current-history CSV.

## W7 — Long/flat-only is a standing blind spot, not a law

`spot_long_flat_only=true` was a per-protocol gate choice that hardened into a
habit; the short side of every tested mechanism is unexplored.

- MUST: declare directional capability (long/flat, short/flat, two-sided)
  explicitly in each new contract, with rationale.
- MUST NOT: justify long/flat with "prior protocols did so"; cite mechanism
  logic or venue constraints instead. (Live short/leverage remains blocked by
  ADR-001/ADR-013 stages regardless.)

## W8 — Ten correlated survivors share one tail

Joint exposure profile: mean 0.95 active signals, max 6 concurrent; all
long-BTC-in-calm-regimes. A calm-regime BTC drawdown hits every survivor at
once; adding the 11th family member raises tail size, not Sharpe.

- MUST: evaluate any promotion at shadow-portfolio level (ADR-014 §6):
  marginal contribution, correlation-adjusted, via
  `apps/ops/research_portfolio_monitor.py` panels.
- MUST NOT: promote a candidate on standalone metrics while its family
  correlation to held survivors is unexamined.

## W9 — Ceremony is not insight; process weight must buy evidence

Per-protocol crontabs, file-set copies (`research_v{n}_*.py`), and a
1,600-line status file grew faster than survivor quality. Heavier process on a
weak hypothesis produces a well-audited weak result.

- MUST: justify each new protocol by mechanism rationale and family
  orthogonality first (ADR-014 §3.4); reuse shared harness modules where they
  exist.
- MUST NOT: copy another protocol's file set as a template without asking
  whether the mechanism deserves a protocol at all; MUST NOT grow
  `docs/project-status.md` with per-protocol narrative (use `docs/progress/`).

## W10 — The factor panel is the program's real asset

48 protocols left behind a SHA256-snapshotted, point-in-time multi-factor
panel (Cboe family, Treasury, premium, basis, on-chain, TVL, attention). Its
reuse cost is zero provider risk; its value compounds across studies.

- MUST: when proposing ML or multi-signal work, first consider the already
  snapshotted panel (ADR-014 §7, backlog B1) before hunting new providers.
- MUST NOT: open a new scraping provider for a factor class the panel already
  covers, without stating why the archived series is insufficient.

---

Cross-references: ADR-014 (normative program rules), `docs/research-mechanism-backlog.md`
(where to explore next), `docs/progress/research-mechanism-family-registry.json`
(what was tried, in which family, with what outcome).
