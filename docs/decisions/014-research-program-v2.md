# ADR-014: Research Program v2 — Mechanism Orthogonality, Benchmark-Relative Gates, and Portfolio-Level Evaluation

- **Status**: Accepted
- **Date**: 2026-08-27
- **Owner**: nishiki (commissioned via operator directive; drafted from the 2026-08-27 program audit)
- **Scope**: How all future alpha research protocols (v49+) are selected, gated, counted, and promoted. Program-level meta-analysis of v2–v48. Portfolio-level evaluation of paper-shadow survivors.
- **Depends on**: ADR-004 (backtest result format), ADR-005 (source taxonomy), ADR-006 (SourcePolicy), ADR-007 (paper runtime).
- **Companion normative files**: `docs/research-program-warnings.md` (agent warnings), `docs/research-mechanism-backlog.md` (exploration backlog), `docs/progress/research-mechanism-family-registry.json` (machine-readable trial registry).

## 1. Context: 2026-08-27 program audit findings

Protocols v2–v48 built an exemplary integrity pipeline (pre-registration, frozen
gates, immutable snapshots, duplicate replays, sealed future blind). The audit
found the *hypothesis* side of the program has structural problems. Each finding
below is normative context: future agents must treat these as established facts
about this program, not re-litigate them.

- **P1 — Survivor homogeneity.** All ten `paper_shadow` survivors are variants
  of one mechanism: "an external risk index declines/relieves over ~5
  observations → long BTCUSDT spot, else flat." V18 and V40 are literally the
  same index (VXN) under two near-identical rules. Signal-panel correlation
  (avg 0.11) understates joint risk: all survivors hold the same position
  (long BTC in calm regimes) and share the same tail (BTC drawdown during low
  external vol). Evidence: `docs/progress/phase-2-research-portfolio-shadow-report.md`.
- **P2 — No benchmark-relative gate.** Historical GATES tested absolute PnL
  (`base_net_pnl > 0`, breadth, leave-best) in windows where BTC mostly rose.
  `alpha_review.py` computes a buy-and-hold benchmark but no gate consumed it.
  A long/flat rule with ~50% exposure passing "positive 2/3 years" during a
  bull market demonstrates beta capture, not timing skill.
- **P3 — Program-level multiple testing.** ~47 protocols and >100 tested
  identities, most from the same relief family, were screened by gates that a
  lucky long-only rule can pass. Per-protocol discipline does not control the
  family-wise error rate across protocols. No global trial registry, deflated
  expectation, or random-timing null existed before this ADR.
- **P4 — Weak statistical power per candidate.** Confirmation PnLs are tens of
  USDT at `trade_size=0.001` BTC over 3 years with 30–209 positions and no
  t-stat/bootstrap gate. `leave-best` is a coarse concentration check only.
- **P5 — Forward shadow window has no performance content.** The 7-day / 50-signal
  forward gate validates data integrity and pipeline freshness. It must never be
  cited as performance evidence.
- **P6 — Data-source structural mismatch.** Cboe/FRED-style sources publish on
  the US trading calendar with 1–2 day lags and no historical vintages, while
  BTC trades 24/7. Weekend signal vacuum is a mechanism-level cap, and vintage
  risk is only mitigated, not eliminated. Binance Vision official archives
  (klines, premium index, funding) are point-in-time by construction and 24/7.
- **P7 — Long/flat-only blind spot.** Every survivor is spot long/flat
  (`spot_long_flat_only=true`). The short/two-sided half of every tested
  mechanism is unexplored.
- **P8 — No portfolio construction.** Survivors are held as independent 0.2x
  candidates. Mean concurrent active signals ≈ 0.95; 40% of days fully idle.
  Per-candidate promotion of tiny-PnL rules to testnet costs more operationally
  than it can return.

## 2. Decision overview

Five workstreams. W1 is implemented with this ADR; W2/W3 are normative
immediately; W4/W5 define contracts for future protocols and reviews.

| Workstream | Content | Status |
|---|---|---|
| W1 | Program meta-analysis of v2–v48 vs benchmark and random-timing null | Tooling + first report committed with this ADR |
| W2 | Mechanism-family registry; relief family declared saturated; orthogonality required at pre-registration | Normative now; registry committed |
| W3 | Gates v2 for all future protocols (benchmark-relative + statistical) | Normative for v49+ |
| W4 | ML restart as one multi-factor panel protocol (not more single-factor scans) | Contract defined; backlog B1 |
| W5 | Portfolio-level evaluation and promotion; ceremony simplification | Normative for promotion reviews; shared-collector spec Draft |

Nothing in this ADR reopens, retunes, or re-gates any sealed protocol (v2–v48),
opens the 2026-09..2027-01 future blind, changes any `SourcePolicy`, or touches
the order path. Existing `paper_shadow` holds continue unchanged under their
already-reviewed policies.

## 3. W2 — Mechanism-family registry and saturation (normative)

3.1 The machine-readable registry lives at
`docs/progress/research-mechanism-family-registry.json` and is built/validated
by `apps/ops/research_family_registry.py`. It maps every tested identity
(protocols v2–v48 plus the original 16-candidate registry) to a mechanism
family, records per-identity outcome, and maintains program totals used for
multiplicity corrections.

3.2 **Family status semantics**:
- `saturated`: no new pre-registration may add members. A protocol whose
  candidate is a member of a saturated family must be rejected at
  pre-registration review, before any data access.
- `deprioritized`: new members require an explicit written justification of
  what is mechanically different from the family's rejected members.
- `open`: eligible for new pre-registrations.
- `blocked_provider`: mechanism untested because providers failed; a new
  attempt requires a genuinely different provider identity.

3.3 **The `external_index_relief` family is declared saturated** as of this
ADR. Membership: any rule whose signal is a short-window (≈2–30 observation)
decline/relief/expansion condition on a non-crypto external index level
(implied vol, implied correlation, strategy/buywrite indices, Treasury yields
or their volatility, financial-stress composites) mapped to long/flat BTC.
This family produced all ten current survivors and dozens of rejects; the
marginal member adds correlated beta, not new alpha. Existing survivor holds
are unaffected.

3.4 **Pre-registration orthogonality requirement.** Every protocol v49+ must
declare, in its frozen contract JSON and before any data access: (a) its
mechanism family (existing `open` family or a new one with a stated economic
rationale), (b) why the mechanism is orthogonal to current survivors (what
state of the world it profits from that the survivor set does not), and
(c) its directional capability (long/flat, short/flat, two-sided). The family
registry must be updated in the same commit that freezes the protocol.

3.5 **Enforcement.** `research_family_registry.py --check` recomputes the
registry from protocol modules and committed results JSONs and fails if any
`apps/ops/research_protocol_v*.py` has no family mapping. The check runs in the
test suite, so adding protocol v49 without registering its family fails CI.

## 4. W3 — Gates v2 for all future protocols (normative for v49+)

Gates v2 = all v48-era gates, with these changes and additions. Sealed
protocols are NOT re-gated; these apply to new pre-registrations only.

| Gate | Requirement | Rationale |
|---|---|---|
| `benchmark_relative_base` | `base_net_pnl > time_in_market_fraction × same_window_buy_and_hold_pnl` at the same fixed trade size | For fixed-quantity long/flat rules, expected random-timing PnL = exposure × B&H; beating it is the minimum claim of timing skill (P2) |
| `bootstrap_p_value` | Stationary-bootstrap / random-timing Monte Carlo p-value of `base_net_pnl` ≤ 0.10, using the two-stage null implemented in `apps/ops/research_meta_analysis.py` | Replaces "positive = pass" (P4) |
| `closed_positions_at_least` | ≥ 60 per evaluation window (was 30) | Statistical power floor (P4) |
| `deflated_expectation_report` | Confirmation review must state the current registry totals (identities evaluated, survivors) and the expected lucky-survivor count from the latest meta-analysis; reviewer must argue the candidate clears it | Program-level multiplicity (P3) |
| `directional_declaration` | Contract declares long/flat, short/flat, or two-sided; "long/flat because that is what we always do" is not acceptable rationale | P7 |
| `weekend_coverage_statement` | Contract states how the data source behaves on weekends/holidays vs 24/7 BTC and quantifies expected signal vacuum | P6 |
| All existing v48 gates | base/stress > 0, years ≥ 2/3, months ≥ 18/36, leave-best > 0, duplicate replays, evidence blockers = 0 | Unchanged |

Cost scenarios (`gross`/`base`/`stress`) are unchanged from
`research_protocol_v48.COST_SCENARIOS`.

## 5. W1 — Program meta-analysis (contract + first run)

5.1 Tool: `apps/ops/research_meta_analysis.py`. It is an **evaluation
artifact, not a trading identity**: it writes no `SignalEvent`, creates no
source/model, mutates no `SourcePolicy`, and must never read the
2026-09..2027-01 future blind. Its price data covers only the already-opened
evaluation windows (2020-01-01..2022-12-31 development, 2023-01-01..2025-12-31
confirmation).

5.2 Benchmark data identity: Binance Vision official monthly `1d` kline
archives for BTCUSDT (spot), fetched once per month-file with recorded SHA256s
(`fetch-closes` subcommand, manifest under `data/meta/`). This is the same
official archive already used by `apps.ops.backfill_bars`.

5.3 The report (`build-report` subcommand) computes, from committed results
JSONs plus the daily closes:
- Buy-and-hold PnL and monthly-breadth of B&H per window at `trade_size=0.001`;
- Per-survivor capture ratio (`base_net_pnl / window_bh_pnl`) and breadth
  comparison vs B&H;
- A two-stage random-timing Monte Carlo null (random long/flat rules with
  survivor-like holding cadence and exposure, v48-era gates applied to the
  development window, then unchanged to confirmation) yielding per-trial pass
  probabilities and the expected number of lucky two-stage survivors given the
  registry's evaluated-identity count;
- Deterministic seed recorded in the output.

5.4 Outputs are committed at
`docs/progress/research-program-meta-analysis-v1.json` and `.md`. The report
feeds a human review. It does not auto-demote any survivor; it calibrates how
much confidence the survivor set deserves and gates W5 promotion decisions.

5.5 Rerun policy: rerun only when the registry totals change (a new protocol
completes) or a new evaluation window is legitimately opened. Reruns append
`-v2`, `-v3` suffixes; prior reports are immutable.

## 6. W5 — Portfolio-level evaluation and promotion (normative)

6.1 The unit of promotion review moves from single candidate to
**shadow portfolio**: the equal-multiplier basket of all current
`paper_shadow` survivors, monitored by `apps/ops/research_portfolio_monitor.py`.

6.2 Any future `paper_shadow → paper_simulated` review must include: (a) the
candidate's marginal contribution to the shadow portfolio (correlation-adjusted,
using the monitor's signal panel), and (b) the latest meta-analysis
lucky-survivor expectation. Standalone absolute PnL is no longer sufficient
review evidence.

6.3 Per-candidate testnet promotion for candidates whose confirmation base PnL
is below 100 USDT (at the standard 0.001 trade size) is deprecated; testnet
effort is reserved for a reviewed portfolio configuration or a candidate with
materially larger evidence.

6.4 Ceremony simplification (Draft): a shared prospective-collector framework
(one daily runner iterating registered collector configs) should replace the
one-crontab-per-protocol pattern; new protocols SHOULD parameterize shared
harness modules instead of copying `research_v{n}_*.py` file sets. This
subsection becomes Accepted when the framework lands; until then new protocols
may still install per-protocol collectors with operator approval.

## 7. W4 — ML restart contract (backlog B1)

The most valuable asset v2–v48 produced is the point-in-time, SHA256-snapshotted
multi-factor panel (Cboe family, Treasury, premium index, basis, on-chain,
TVL, attention series). The FreqAI/ML layer restarts as **one** pre-registered
protocol over that panel, not as more single-factor scans:

- Model class: regularized multi-factor (penalized linear or gradient
  boosting), daily or 4h horizon, nested walk-forward with embargo;
- Data: only already-snapshotted factor series plus official Binance archives;
  no new scraping providers in the first iteration;
- Gates: Gates v2 (§4) including the bootstrap and benchmark-relative gates;
- Identity: new `freqai_*` source under ADR-005; frozen before any training;
- The sealed future blind stays sealed.

Full draft requirements live in `docs/research-mechanism-backlog.md` §B1.

## 8. Agent-facing warnings

`docs/research-program-warnings.md` is the distilled warning list from this
audit. It is **Always Read** for any research, gating, or promotion task, and
is wired into `docs/agent-reading-list.md`. When a future audit adds a warning,
update that file, not this ADR.

## 9. What this ADR does NOT do

- Does not reopen, retune, ensemble, or re-gate any sealed protocol v2–v48.
- Does not open the 2026-09..2027-01 future blind.
- Does not change any `SourcePolicy`, stage, or collector currently installed.
- Does not authorize testnet or live trading (ADR-008/ADR-013 gates unchanged).
- Does not demote current `paper_shadow` survivors; W1's report informs a
  separate human review.

## 10. Acceptance checklist

- [x] `docs/research-program-warnings.md` committed and wired into the reading list.
- [x] `docs/research-mechanism-backlog.md` committed with ranked orthogonal axes.
- [x] `apps/ops/research_family_registry.py` + committed registry JSON; `--check` green in tests.
- [x] `apps/ops/research_meta_analysis.py` + first committed report (JSON + MD).
- [x] `docs/project-status.md` updated; reading list rows added.
- [ ] First Gates-v2 protocol (v49+) pre-registered under §3.4/§4 (future work).
- [ ] Shared collector framework (§6.4) implemented (future work).
