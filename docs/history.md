# Project History

A condensed record of what was built, what was learned, and why material was
archived. Full detail for everything before 2026-10-17 is in tag
`archive/pre-slim-2026-10-17` (`docs/progress/`, research retros, old status).

## Timeline

| Date | Milestone |
|---|---|
| 2026-05-14..17 | Phase 0/1: ADR-001..008, `SignalEvent v1` bridge, Nautilus backtest runner, result format, source taxonomy, gray-rollout `SourcePolicy`, paper runtime |
| 2026-05-19..06-01 | Phase 3 testnet canary for `freqai_linear_v1`. Fifteen 6-hour canaries ran, with incidents: signal lag, duplicate same-bar entries, a runner that disappeared. The strict 14-day streak never started |
| 2026-05-21 | Observability stack (Prometheus/Grafana/Loki) and Postgres brought up early. ADR-010/011 (Redis, Postgres mirror) stay Draft |
| 2026-06-04 | ADR-009 AgentAdvice audit store, ADR-012 read-only dashboard (Phase 4/5 entry) |
| 2026-06-29 | ADR-013 Phase 6 live-risk gate (Draft) and passive live-readiness / startup-guard |
| 2026-07..08 | Research protocols v2–v48. Ten survivors went to paper shadow; v5 collector deployed to the cloud |
| 2026-07-29 | `freqai_linear_v1` demoted to `paper_simulated`; canary paused |
| 2026-08-27 | Program audit → ADR-014 Gates v2, warnings W1–W10, meta-analysis: survivors are consistent with luck |
| 2026-08-27..09 | v49–v53 under Gates v2: all rejected |
| 2026-09-07/08 | Shadow collectors pinned to clone `1727408`; 500 USDT planning budget (50% drawdown, 50 USDT/day preference) |
| 2026-09-09..11 | Portfolio execution plan, ADR-015 unified risk policy, ADR-016 testnet observation admission, ADR-017 engineering session |
| 2026-09-11 | One Binance Spot testnet BUY (0.0001 BTC LIMIT at 76,908.15) was accepted and canceled after 2.0 s with no fill. All 502 assets reconciled. The one-BUY allowance is consumed |
| 2026-09-13..28 | Joint account+market collection and egress-guard chain (details below). Never authorized to collect for real |
| 2026-10-17 | Shadow cron migrated to this host; repository slim-down |

## Testnet engineering session (ADR-015..017)

What works and is proven on the real testnet: Ed25519-signed REST and user
stream, a full-account snapshot (502 assets, 500 valued), a native Nautilus
order lifecycle for one LIMIT BUY with cancellation, deterministic
reconciliation and an archive replay. Fills, fees, cleanup SELL and active
recovery were only tested synthetically. Qualified equity and the UTC
day-open baseline remain unproven: two assets are unpriced, 65 exceed
top-book depth, and the provider has no reset history.

## Egress / joint-window chain (archived)

Between 09-13 and 09-28 roughly 60k lines went into proving that one future
joint collection would stay inside Binance rate limits and egress rules. The
work covered a rate-evidence parser, a local TLS/WS transport, an attempt
ledger and signed reservations, a dedicated-UID gateway, fixtures v14–v27
(19/19 operations), nftables blackout windows and namespace audits. None of
it reached an operational host controller. Admission stayed blocked:
provider-visible source and all-caller egress were unproven, and 496 assets
were outside the pilot.

Why it was archived: no strategy needs a full-account real-time collection
yet. This work violated Iron Rule 1 (no optimization before alpha). Code and
evidence references are under `apps/strategies_nautilus/portfolio_*`,
`apps/ops/portfolio_*` and `infra/egress-guard/` in the archive tag. The
evidence files themselves are still in `data/egress-*` and `data/installed-*`.

## Lessons

1. Prove alpha before engineering for scale. 140k lines of research and
   verification code produced no tradable edge.
2. Benchmark everything against buy-and-hold and a random-timing null (W1, W3).
3. One mechanism, one module. Per-version file copies made the repo
   unreadable and unreviewable (W9).
4. Status files are dashboards, not changelogs. The agent reading list had
   grown to 129 KB and the status file to 59 KB.
