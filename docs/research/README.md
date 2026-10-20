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
| [round-2026-10.md](round-2026-10.md) | Current round: v54 trend + inverse-vol, v55 order flow; how stages run |
| [round-2026-10b.md](round-2026-10b.md) | Next round: v56 taker persist, v57 deleveraging rebound, v58 xs taker rotation, v59 turn of month |
| [round-2026-10c.md](round-2026-10c.md) | Intraday round (ADR-018): v60 cascade rebound |
| [round-2026-10d.md](round-2026-10d.md) | Intraday round: v61 BTC-led laggard catch-up |
| [contracts/](contracts/) | Frozen protocol contracts (v54+) |
| [family-registry.json](family-registry.json) | Every protocol, identity, family and outcome through v53 |
| [meta-analysis-v2.md](meta-analysis-v2.md) | Buy-and-hold benchmark, random-timing null, program multiplicity |

## What was learned (v2–v53, 2026-05..09)

- 60 protocols, 163 identities, 125 opened for PnL, 36 blocked by data providers (through v61).
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
- **Round 2026-10 (v54–v55)**, with the shared harness `apps/research/`: multi-coin
  trend with inverse-vol passed development (p 0.016) but failed confirmation
  (p 0.295; shorts lost in five of six years). BTC taker-flow continuation
  missed development on p (0.115) after costs ate 62% of gross; OI squeeze lost.
- **Round 2026-10b (v56–v59)**: taker persistence, deleveraging rebound and
  10-coin taker rotation failed development; turn of month passed development
  (p 0.010) and failed confirmation (p 0.224, unstable day pattern). A cost study
  showed lower fees raise net PnL but not timing significance (p barely moves).
- **Round 2026-10c (v60, intraday, ADR-018)**: buying spot after a 60-minute
  price and open-interest cascade beat random timing (p 0.0002) but earned about
  one round trip of costs (gross +1,560, base +124, stress −832) and lost in
  2022; rejected in development.
- **Round 2026-10d (v61, intraday)**: buying the coins that lagged a BTC surge
  earned about 0.14% gross per trade against a 0.24% round trip (base −4,083);
  rejected in development. Per the stopping rule set before the freeze, the
  alpha search stopped on 2026-10-20.

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

They ran daily as paper shadows from a clone pinned at commit `1727408c` until
2026-10-18, when the crons and all collected forward data were removed. The
2026-09..2027-01 blind will not complete, so none of them is a candidate.

## Archived code

Protocol code, collectors, reviews and per-protocol progress reports live in
tag `archive/pre-slim-2026-10-17`:

- `apps/ops/research_*.py` — protocol contracts, snapshots, reviews, shadow
  runtime, portfolio monitor, meta-analysis, family-registry checker.
- `apps/strategies_freqtrade/research/` — signal exporters for every mechanism.
- `infra/research-v*/` — collector deployment templates.
- `docs/progress/phase-2-research-*` and the research retros in `docs/retros/` — per-protocol records.

Read single files with `git show archive/pre-slim-2026-10-17:<path>`. Reviving
a shadow collector means redeploying from the archive tag (or commit `1727408c`)
and starting its forward collection from scratch.
