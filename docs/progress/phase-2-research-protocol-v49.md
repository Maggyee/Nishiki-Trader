# Research Protocol v49 — Multi-Factor Panel Ridge (ADR-014 / backlog B1)

- **Status**: Pre-registered (frozen before factor values were opened)
- **Date frozen**: 2026-08-27
- **Mechanism family**: `multifactor_ml` (first member; registered in
  `docs/progress/research-mechanism-family-registry.json`)
- **Identity**: `freqai_panel_ridge_v1 / panel17-ridge-mwf-oos2020h2-v1`
- **Contract**: `apps/ops/research_protocol_v49.py` (constants + pinned SHA256s;
  `contract_sha256()` is recorded in every stage output)
- **Pipeline**: `apps/ops/research_v49_multifactor.py` (`qualify` → `develop` → `confirm`)
- **Gates**: Gates v2 per ADR-014 §4 (first protocol run under them)

## 1. Hypothesis and orthogonality (ADR-014 §3.4)

Every sealed single-factor rule mapped ONE archived series through a fixed
short-window condition to long/flat BTC, and the program meta-analysis showed
that family's survivors are indistinguishable from lucky beta timing. The
untested hypothesis is that the *combination* of the archived point-in-time
factors carries conditional next-day information no single factor carried.
This candidate learns a signed cross-factor conditional expectation (ridge
regression); it reuses archived inputs but no sealed rule's condition,
threshold, or identity, and it profits only in states (factor combinations)
that no `external_index_relief` member expresses.

- **Directional declaration**: signed model scores; execution spot long/flat
  only in this protocol (paper-stage venue parity). Short expression deferred
  to a separate `two_sided_regime` study (backlog B4).
- **Weekend coverage**: external factors are used strictly at their archived
  point-in-time `available_at` stamps (which encode each source protocol's
  publication lag) and forward-filled at most 7 calendar days; BTC-native
  features update 24/7. Weekend positions carry Friday-aged external
  information by construction.

## 2. Frozen inputs

- 17 archived factor series, each as its sealed dev + confirmation snapshot
  pair with SHA256 pinned in `FACTOR_SOURCES` (GVZ, VXN, VXD, VXGOG, VIX6M,
  VIX1Y, COR1M, COR1Y, FVX, OFR safe-asset stress, VPN, LOVOL, BXN, CLL,
  all-chain TVL, BTC premium index, BTC perp basis). Pre-freeze reads were
  limited to file hashes, headers, row counts, and date coverage — no values.
- Labels/execution/benchmarks: Binance Vision official spot 1d klines
  2019-12..2025-12, CHECKSUM-verified via
  `apps.ops.research_meta_analysis fetch-closes` into
  `data/research-v49/closes/`.

## 3. Frozen method

Daily panel on the BTC UTC calendar; per-external-factor feature = 5-panel-day
difference then expanding z-score (min 60 obs); native features `btc_mom20`,
`btc_rvol20`. Label = next-day log return. Ridge regression (closed form,
unpenalized intercept), monthly-refit expanding walk-forward from 2020-01-01
with min 6 training months. Alpha grid {1, 10, 100, 1000, 10000} selected
nested inside development OOS by base net PnL (ties → larger alpha), then
frozen for confirmation. Signal: predicted return > 0 → long next day, else
flat; 0.001 BTC; gross/base/stress costs identical to v48.

## 4. Windows and gates

| Stage | Window | Months gate | Other gates |
|---|---|---|---|
| Development OOS | 2020-07-01..2022-12-31 (30 months) | ≥15/30 | base>0, stress>0, ≥2/3 years, ≥60 positions, leave-best>0, base > exposure×B&H, bootstrap p ≤ 0.10, 2 duplicate replays |
| Confirmation | 2023-01-01..2025-12-31 (36 months) | ≥18/36 | same, with frozen alpha, single shot |

Bootstrap null: 20,000 random Markov long/flat trials with exposure/holding
ranges centered on the candidate's realized values (spec in
`BOOTSTRAP_SPEC`); p = (1 + #{null base ≥ candidate base}) / (n+1).

Confirmation opens only if development passes. A confirmation failure closes
the protocol permanently: no retuning, no grid extension, no ensemble, no
factor-list edits under this identity. If the model cannot clear Gates v2,
the ML layer stays empty (ADR-014 §7) — the fallback is backlog B2, not a
weaker variant of this protocol.

## 5. Boundaries

No `SignalEvent` writes, no `SourcePolicy` changes, no sealed-protocol
reopening (archived snapshots are read-only inputs), no future-blind access
(2026-09..2027-01 stays sealed), no live-path impact. Development results and
confirmation results land in
`docs/progress/phase-2-research-v49-{provider-qualification,development-results,confirmation-results}.json`.
