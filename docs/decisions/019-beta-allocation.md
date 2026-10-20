# ADR-019: Beta allocation track (market exposure with risk control)

- **Status**: Draft, awaiting operator acceptance. The admission criteria in §3
  were committed before the historical comparison in §5 was run.
- **Date**: 2026-10-20
- **Authority**: The stopping rule set before v61 was frozen ("if v61 fails,
  the alpha search stops and the project moves to a beta-with-risk-control
  allocation"); after v61 failed, the operator said "可以，开始写ADR并做历史比较".
- **Relates to**: ADR-001 (Iron Rules, capital ladder), ADR-005 (source names),
  ADR-014 (alpha gates, unchanged), ADR-015 (portfolio risk limits),
  [warnings](../research/warnings.md) W1.

## 1. Context

- Alpha search: 60 protocols, 163 identities, none passed ADR-014 gates. The two
  intraday protocols found real but small effects, about one round trip of retail
  taker costs or less ([round 2026-10c](../research/round-2026-10c.md),
  [2026-10d](../research/round-2026-10d.md)).
- In the 2023–25 learning simulation, holding the coins made more than any timed
  strategy (+20,150 against +11,753 for v54 long/flat with notional sizing), with
  three times the drawdown (20,679 against 6,935).
- The realistic source of return for this project is the market itself. What a
  system can add is discipline: sizing, exits in bear markets, hard loss limits,
  and an auditable record.

## 2. Decision

2.1 A strategy may be declared **beta**: it claims no timing skill and is never
described as alpha (W1). It is a `rule` source under ADR-005, with `beta` in its
name (e.g. `rule_beta_sma200_v1`). ADR-014 gates do not apply to it; §3 does.

2.2 Beta strategies are long/flat on spot only, gross exposure at most 1, built
from public daily prices, with parameters that are classic or already frozen.
No parameter search on the evaluation history.

2.3 Path: historical admission (§3) → local paper run (§4) → Spot testnet → real
money only through the ADR-001 capital ladder and ADR-015 limits, each step a
separate operator decision. This ADR authorizes no testnet key and no real money.

## 3. Historical admission criteria (fixed before evaluation)

Evaluation: Binance spot daily closes, 2020-01-01 to 2025-12-31 (includes the
2022 bear market), starting equity 10,000 USDT, compounding. Target weights are
a fraction of equity, decided at a day's close and traded at that close; units
are held between rebalances; costs 12 bps per unit of traded value (stress 20).

Benchmark: buy-and-hold of the same universe at equal weight, bought on
2020-01-01 and never rebalanced.

A candidate is admitted only if all hold against its own benchmark:

1. Maximum drawdown at most two thirds of the benchmark's.
2. CAGR divided by maximum drawdown at least the benchmark's.
3. Loss in calendar 2022 at most half the benchmark's 2022 loss.
4. CAGR at least half the benchmark's CAGR (it must actually hold the market).
5. Positive total return under stress costs.

Candidates named before evaluation:

- **B1**: v54 trend with inverse-volatility sizing, long/flat (negative weights set
  to 0), 10 coins, frozen v54 parameters, weekly rebalance. Benchmark: 10 coins.
- **B2**: BTC and ETH, 50% each, each held only while its close is above its
  200-day simple moving average, checked daily. Benchmark: BTC/ETH 50/50.

Both are reported whatever the outcome.

## 4. Paper and testnet requirements

- The paper runner treats sell signals on spot as closes, as the Nautilus
  strategy already does on CASH accounts (gap noted 2026-10-18).
- Local paper for at least four weeks, holdings matching the daily replay.
- Spot testnet with a new Ed25519 key for at least 14 days without manual
  intervention (ADR-001 stage 0) before any real-money decision.
- ADR-015 limits apply at every stage. A live drawdown beyond the historical
  maximum drawdown triggers a stop and an operator review.

## 5. Historical comparison

Pending; filled in by the comparison commit.

## 6. What this ADR does not do

- Does not change ADR-014 or reopen any rejected identity.
- Does not authorize testnet keys, real money or perpetuals.
- Does not add services or data sources beyond Binance public archives.
