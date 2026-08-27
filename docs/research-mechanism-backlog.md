# Research Mechanism Backlog

- **Status**: Active
- **Owner**: nishiki
- **Purpose**: Ranked, agent-readable backlog of orthogonal mechanism axes for future pre-registrations (protocols v49+). Every entry names its family per `docs/progress/research-mechanism-family-registry.json` and must be pre-registered under ADR-014 §3.4 and Gates v2 (§4) before any data access.
- **Ranking key**: economic rationale strength × orthogonality to the current survivor set × data quality (official/immutable/24-7) × statistical power available.

Entries are proposals, not authorizations. Opening any entry requires a new
frozen protocol identity. Nothing here may reuse or retune a sealed protocol's
fingerprints, and the 2026-09..2027-01 future blind stays sealed for every
entry.

---

## B1 — Multi-factor ML on the archived point-in-time panel (W4 restart) — PRIORITY 1

- **Family**: `multifactor_ml` (new; supersedes `linear_ml`).
- **Mechanism**: cross-factor conditional expectation of daily/4h BTC returns,
  learned from the program's already-snapshotted factor panel (Cboe vol
  family, Treasury yields/vol, implied correlation, premium index, basis,
  on-chain, TVL, attention). Single-factor timing failed repeatedly; the
  untested hypothesis is that the *combination* carries signal.
- **Data**: only already-snapshotted series + official Binance archives. Zero
  new scraping providers in iteration 1 (Warning W10).
- **Pre-registration must fix**: factor list (by existing snapshot SHA256s),
  model class (penalized linear or gradient boosting), nested walk-forward
  splits with embargo ≥ max factor lag, feature lags respecting each factor's
  publication calendar, Gates v2 in full, new `freqai_*` identity per ADR-005.
- **Directional capability**: two-sided scores; execution long/flat in paper
  stages (venue stage caps unchanged).
- **Power**: daily panel 2020–2025 ≈ 2,190 observations; expect hundreds of
  positions.
- **Failure criterion to respect**: if the panel model cannot beat the Gates v2
  benchmark-relative and bootstrap gates, the ML layer stays empty; do not
  fall back to single-factor scans.

## B2 — Funding-rate mechanisms (crypto-native carry/positioning) — PRIORITY 2

- **Family**: `crypto_derivatives_structure` (open; v45/v46/v48 are members —
  the only crypto-native family with a confirmed survivor).
- **Mechanism**: perpetual funding as crowded-positioning signal — funding
  momentum, extremes, and mean-reversion after funding spikes; funding is a
  *paid* number, not a survey.
- **Data**: Binance Vision official `fundingRate` monthly archives (USD-M),
  8h cadence, 24/7, point-in-time by construction. `apps/ops/backfill_funding.py`
  already exists from the earlier flow-positioning study (family history:
  original `flow_positioning` candidate was rejected — a new identity must
  state what differs, e.g., horizon, conditioning, or extremes vs levels).
- **Directional capability**: two-sided by nature (positive extreme →
  short-biased state; negative extreme → long-biased state); declare
  explicitly.
- **Power**: 8h series 2020–2025 ≈ 6,570 observations.

## B3 — Cross-sectional relative value across top-N liquid perps — PRIORITY 3

- **Family**: `cross_sectional_relative` (open — nothing in protocols v2–v48
  is cross-sectional; v41's single ETH/BTC ratio rule is not a portfolio. The
  legacy 16-candidate era rejected four long-only rotation rules
  (`rule_xs_momentum_rotation_v1`, `rule_relative_value_rotation_v1`,
  `rule_alt_diversified_momentum_v1`, `rule_alt_low_vol_rotation_v1`); a
  market-neutral long/short construction is the untested part).
- **Mechanism**: relative momentum / relative basis / relative funding across
  10–20 liquid USDT perps, long top-k vs short bottom-k (or long/flat vs BTC
  in early stages). Orthogonal by construction: market-neutral leg removes the
  long-BTC beta that all current survivors share.
- **Data**: Binance Vision daily klines + funding for the universe; universe
  membership frozen by a liquidity rule *as of the freeze date* (survivorship
  guard: use symbols listed through the whole window or handle listings
  point-in-time).
- **Pre-registration must fix**: universe rule, ranking factor, k, rebalance
  cadence, cost model per leg, and the netting treatment in the
  cash-replay harness (needs a multi-instrument extension — implementation
  cost is real; state it).
- **Power**: N symbols × daily = an order of magnitude more observations than
  any BTC-only rule.

## B4 — Two-sided regime rules: the unexplored short side — PRIORITY 4

- **Family**: `two_sided_regime` (new membership axis over existing signals).
- **Mechanism**: current survivors go flat when external risk indices rise;
  the untested half is whether those same states carry negative BTC drift
  (short perp) rather than merely zero exposure. Also covers vol-spike →
  short mean-reversion entries.
- **Constraint**: shorts exist only in paper/backtest until ADR-001/ADR-013
  stages allow more; `spot_long_flat_only` gates must be replaced by explicit
  two-sided gates in the contract (net exposure caps, funding cost of shorts
  included in the cost model).
- **Warning**: this is adjacent to the saturated family — the pre-registration
  must NOT reuse any sealed identity's exact index+window fingerprint
  (W2/W3); propose genuinely different conditioning (e.g., crypto-native
  states from B2) first.

## B5 — Event/calendar structure — PRIORITY 5

- **Family**: `event_calendar` (new).
- **Mechanism**: deterministic clock effects — funding settlement times
  (00/08/16 UTC), US equity open/close overlap, weekend liquidity regime,
  month-end. Signals are clock-driven, so point-in-time is trivial and
  provider risk is zero.
- **Data**: Binance Vision klines only.
- **Power**: very high (every day contributes); effect sizes likely small —
  the Gates v2 bootstrap gate is the honest filter.
- **Note**: fee-dominated by design risk — run the base/stress cost scenarios
  first on paper napkin math before freezing a protocol.

## B6 — Open interest / taker-flow imbalance — PRIORITY 6

- **Family**: `microstructure_flow` (open; v6 book-depth was provider-blocked,
  which does not condemn the family).
- **Mechanism**: OI expansion/contraction vs price (crowding vs de-risking),
  taker buy/sell imbalance from official klines (taker buy volume column).
- **Data**: taker volume — Binance Vision klines (already archived, zero new
  provider risk). OI — Binance Vision `metrics` archives exist only from
  ~2021-12 and must pass a coverage qualification (v28's 700-observation
  lesson: verify coverage BEFORE freezing evaluation windows; shorter windows
  need a pre-registered adjusted window, not a waiver).
- **Directional capability**: two-sided.

## B7 — Volatility-targeted sizing overlay on the shadow portfolio — PRIORITY 7

- **Family**: `portfolio_overlay` (new; not an alpha identity).
- **Mechanism**: not a new signal — scale the shadow portfolio's target
  exposure by inverse realized vol. For low-frequency long/flat rules, sizing
  may matter more than the next signal. Runs entirely at the
  `research_portfolio_monitor` level; no new SignalEvents.
- **Contract**: define as a portfolio evaluation study under ADR-014 §6, not a
  tradable source; success = higher portfolio-level risk-adjusted numbers on
  the same signals in shadow replay.

## B8 — Stablecoin liquidity expansion (existing forward candidate) — HELD

- **Family**: `stablecoin_liquidity` (open; v12 forward contract active).
- **Status**: already registered as `forward_data_candidate` with 0/180 days
  of genuine forward evidence. Nothing to do except keep the v12 discipline;
  listed here so agents do not re-propose it as "new" (W2).

---

## Anti-backlog (do not propose)

- Any new member of `external_index_relief` (saturated — ADR-014 §3.3).
- Single-factor TA long/flat on BTC daily/hourly (family `crypto_price_ta`:
  v41/v43/v44 + original registry rejects).
- Attention/sentiment level rules (v23/v24/v29 rejects; new attention work
  needs a genuinely different mechanism statement, not a new article list).
- Provider retries banned by sealed protocols (v6, v14, v15, v17, v21, v28,
  v31, v32 identities).
