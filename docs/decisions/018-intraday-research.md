# ADR-018: Intraday research protocols (minute data, hour-scale holds)

- **Status**: Accepted 2026-10-20 by the operator ("4小时，按你说的来算": a
  four-hour minimum holding period; the cost levels as drafted).
- **Date**: 2026-10-18
- **Authority**: After rounds 2026-10 and 2026-10b, the operator chose to look for
  alpha in minute-level data ("b，如果找分钟级的数据需要怎么做", then "可以，先做1和2，
  ADR也起草"). Harness support (data layer, bar-level replay and null) was
  implemented with the draft.
- **Extends**: ADR-014 (Gates v2 and §11 adaptive breadth). Every ADR-014 rule and
  warning W1–W10 applies unless this ADR says otherwise.

## 1. Context

- Daily research is exhausted for now: 58 protocols, 161 identities, 123 opened
  for PnL, none passed. Lower fees raise net PnL but not timing significance
  ([round 2026-10b](../research/round-2026-10b.md), cost study).
- Costs, not data, bound intraday work. BTC spot in 2025, median absolute move
  over the horizon, against one round trip (spot 0.15% with BNB, 0.24% at the
  research assumption of 12 bps per fill; USD-M taker about 0.10%):

  | Horizon | 1 min | 5 min | 1 h | 4 h | 1 day |
  |---|---|---|---|---|---|
  | Median move | 0.025% | 0.058% | 0.20% | 0.41% | 1.14% |

  Taker strategies that hold for minutes cannot cover costs. Market making needs
  order-book data and latency this architecture does not have (signals go through
  the SignalEvent bridge; execution is Nautilus taker orders).
- Binance Vision archives checked on 2026-10-18:

  | Data | Coverage | Size | Use |
  |---|---|---|---|
  | 1m klines, spot and USD-M (incl. taker buy volume) | spot 2017+, USD-M 2020+ | ~2 MB per symbol-month | primary |
  | USD-M metrics, 5-minute OI and ratios | 2021-12+ | small | yes |
  | USD-M bookDepth snapshots | 2023-01+ | ~0.4 MB per day | later, short history |
  | aggTrades | full | 0.5–0.6 GB per BTC month | no (volume) |
  | USD-M bookTicker | 2023-05..2024-03 only | large | no (coverage) |

## 2. Decision

2.1 **Scope.** Signals may use 1-minute klines and 5-minute metrics. Every
position is held at least four hours by construction (a minimum hold in the
mechanism, covered by its tests); sub-hour holds and maker-fill assumptions are
out of scope. Four hours rather than one: the median BTC move over one hour
(0.20%) is about one round trip of costs, over four hours (0.41%) about twice. The replay bar is declared in the contract
(`"bar"`: `1min`, `5min`, `15min` or `1h`).

2.2 **No look-ahead.** Kline rows are indexed by bar open time; the decision for
row t is made at that bar's close (t + bar). A point observation stamped s (e.g.
metrics) is usable at row t only if s ≤ t + bar. Mechanism tests must cover this.

2.3 **Execution lag.** For bars shorter than one hour, `execution_lag_bars` ≥ 1:
the position decided at row t starts earning at bar t+2, one bar later than
the daily convention.

2.4 **Costs per fill.** Spot: base 12 bps, stress 20 bps. USD-M: base 7 bps
(5 taker + 2 slippage), stress 12 bps, with funding charged at each settlement
(longs pay, shorts receive). A USD-M candidate that passes still needs a separate
ADR before perpetuals enter the execution path.

2.5 **Timing null.** The circular-shift null of ADR-014 stays (5,000 trials), with
the shift unit frozen per contract:
- `"day"` for state- or event-triggered mechanisms (flow, OI, price shocks).
  Whole-day shifts keep the time-of-day profile, so a plain intraday seasonality
  cannot pass as event timing.
- `"bar"` only for mechanisms whose stated claim is time-of-day or calendar
  timing.

2.6 **Activity.** `closed_positions_at_least` stays at 60. Added:
`active_days_at_least: 60` per window (distinct UTC days holding a position),
so a few clustered days cannot carry a candidate.

2.7 **Windows.** Unchanged: development 2020-01-01..2022-12-31 and confirmation
2023-01-01..2025-12-31; metrics-based protocols use 2022–23 and 2024–25. The blind
from 2026-09-01 stays sealed. Intraday candidates accumulate positions quickly, so
a short blind stage becomes informative; opening it for a confirmed candidate
needs its own operator decision.

2.8 **Multiplicity.** Intraday identities join the same family registry and
totals. Each round freezes at most three identities. An intraday version of a
rejected daily mechanism (e.g. v57 deleveraging) is a new identity in that
family and needs the W2 justification; its result is read in light of W3.

2.9 **After a pass.** Before paper: a Nautilus backtest on 1-minute bars with
next-bar fills must match the research replay, as the daily learning simulation
did. The order path, SignalEvent v1 and risk controls are unchanged.

## 3. Harness support

`apps/research/`: datasets `spot_klines_1m`, `um_klines_1m`, `um_metrics_5m`;
a versioned parquet cache of parsed archives; contract fields `bar`,
`execution_lag_bars` and `null.shift_unit`; funding bucketed per bar at
settlement; the `active_days` metric and optional `active_days_at_least` gate.
Daily contracts replay exactly as before.

## 4. What this ADR does not do

- Does not freeze or open any protocol, or read any minute-level strategy PnL.
- Does not open the sealed blind, change any SourcePolicy, or touch the order
  path.
- Does not add services, databases or downloads beyond the public archives.

## 5. Operator decisions (2026-10-20)

1. Minimum holding period four hours (2.1); the draft proposed one.
2. Cost levels in 2.4 accepted as drafted.
3. The first round's mechanisms are proposed separately and need approval
   before any freeze.
