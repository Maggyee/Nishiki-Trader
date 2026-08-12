# Phase 2 Research Protocol v14

- **Frozen**: 2026-08-12 before opening the Coin Metrics valuation time-series body.
- **Status**: blocked at provider qualification; no metric value or PnL opened.
- **Trading effect**: none.

V14 locks three BTC mechanisms that were not tested in v13: realized-cap 7/30
expansion, adjusted-NVT 7/30 compression, and seven-observation SOPR below the
structural break-even value of one. They represent aggregate holder cost-basis
growth, improving network utility relative to valuation, and realized-loss
capitulation respectively.

The official Community catalog was inspected without opening metric values and
shows BTC daily coverage spanning the full development window for
`CapRealUSD`, `NVTAdj`, and `SOPR`. The exact time-series request and rules are
frozen together. Observations for UTC day D become usable only at D+2 00:00
UTC. Present-day history is finalized-ledger reconstruction evidence, not a
historical provider-vintage claim, and missing rows are never filled.

The 2020-2022 development reserve opens once after qualification. A candidate
must pass cost, year/month breadth, 30-position activity, leave-best
concentration, long/flat lineage, verified Binance downtime, and duplicate
replay gates before its 2023-2025 confirmation may open. V12 forward data,
completed v13, GVZ paper shadow, and the shared future blind remain separate.

## Provider outcome

The exact request was opened once from clean pushed commit `0ec5333`. The
Community API returned HTTP 403 before any metric row, naming `CapRealUSD` as
unavailable with the supplied public credentials. A follow-up read of the
Community-scoped `/v4/catalog/assets?assets=btc` metadata lists none of
`CapRealUSD`, `NVTAdj`, or `SOPR`; the earlier catalog-all result described
product coverage, not Community entitlement.

V14 therefore stops at provider qualification. No factor value, signal,
position, PnL, confirmation data, or future-blind data was opened. Retrying the
same request, dropping one metric after the response, substituting a paid key,
or silently replacing these metrics would violate this identity.
