# Research Program Summary

- **Status**: Active (conclusions); protocol code archived 2026-10-17
- **Current phase**: Phase 2 research — no strategy has shown alpha
- **Boundaries**: Research produces `SignalEvent v1` only (ADR-002). New
  protocols follow ADR-014 Gates v2 and [warnings](warnings.md) W1–W10.
- **Next entrypoint**: Pick an untried [backlog](backlog.md) entry with the
  operator, pre-register it, and put the exporter under `apps/strategies_freqtrade/`.

## Files

| File | Content |
|---|---|
| [warnings.md](warnings.md) | W1–W10 program warnings. Mandatory for research, gating and promotion work |
| [backlog.md](backlog.md) | Ranked mechanism ideas. B1–B3 have been tried (v49–v53) |
| [family-registry.json](family-registry.json) | Every protocol, identity, family and outcome through v53 |
| [meta-analysis-v2.md](meta-analysis-v2.md) | Buy-and-hold benchmark, random-timing null, program multiplicity |

## What was learned (v2–v53, 2026-05..09)

- 52 protocols, 154 identities, 116 opened for PnL, 36 blocked by data providers.
- **Gates v1 (v2–v48)** left ten survivors, run as paper shadows until 2026-10-18. All ten are
  long BTC when an external index is calm. Eight share one family
  (`external_index_relief`, now saturated). Confirmation PnL is +13.7 to
  +70.7 USDT over three years at 0.001 BTC, and buy-and-hold made +71.0.
  The random-timing null expects 7.98 lucky survivors; P(≥10 by luck) = 0.275.
- **Gates v2 (v49–v53)** added benchmark-relative, bootstrap and position-count
  gates. Everything failed: v49 panel ridge (development), v50 funding
  (provider), v51 funding states (development), v52 cross-sectional (development),
  v53 cross-sectional momentum (confirmation).
- The reusable asset is the point-in-time factor panel (W10), not the rules.

## Gates-v1 survivors (shadow stopped 2026-10-18)

| Protocol | Model version | Family |
|---|---|---|
| 8 | `cboe-gvz5obs-negative-1d-v1` | external_index_relief |
| 16 | `treasury-nominal10-absdiff5-20-negative-lag2d-v1` | external_index_relief |
| 18 | `cboe-vxn-ohlc5obs-negative-1d-v1` | external_index_relief |
| 22 | `cboe-cor1m-diff5-negative-lag1d-v1` | external_index_relief |
| 34 | `cboe-fvx-diff5-negative-lag1d-v1` | external_index_relief |
| 36 | `cboe-vpn-diff5-positive-lag1d-v1` | external_index_relief |
| 40 | `cboe-vxn-diff5-negative-lag1d-v1` | external_index_relief |
| 42 | `cboe-vix6m-diff5-negative-lag1d-v1` | external_index_relief |
| 46 | `crypto-btc-prem-diff5-negative-lag1d-v1` | crypto_derivatives_structure |
| 48 | `crypto-btc-basis-below-ma10-lag1d-v1` | crypto_derivatives_structure |

They ran daily as paper shadows from the pinned clone
`data/collector-deployments/1727408c3b2e960e5b2d544117ee820fcf0375fe` until the
crons were removed on 2026-10-18. The 2026-09..2027-01 blind will not complete,
so none of them is a candidate. Forward data to 2026-10-17 stays in
`data/research-*`; it was a pipeline check, not performance evidence (W5).

## Archived code

Protocol code, collectors, reviews and per-protocol progress reports live in
tag `archive/pre-slim-2026-10-17`:

- `apps/ops/research_*.py` — protocol contracts, snapshots, reviews, shadow
  runtime, portfolio monitor, meta-analysis, family-registry checker.
- `apps/strategies_freqtrade/research/` — signal exporters for every mechanism.
- `infra/research-v*/` — collector deployment templates.
- `docs/progress/phase-2-research-*` and the research retros in `docs/retros/` — per-protocol records.

Read single files with `git show archive/pre-slim-2026-10-17:<path>`. To
revive a shadow collector, work from the archive tag or the pinned clone, not
from main.
