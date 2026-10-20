# ADR-019: Beta allocation track (market exposure with risk control)

- **Status**: Accepted 2026-10-20 by the operator ("批准"), including the sizing
  proposed in §5: B2 at 40% exposure, rebalanced weekly. The admission criteria
  in §3 were committed before the historical comparison in §5 was run.
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

## 5. Historical comparison (2026-10-20)

Run with `uv run python -m apps.research.beta` after the code was committed and
Codex-reviewed (a709c85). File: [results/beta-2026-10.json](../research/results/beta-2026-10.json).
Starting equity 10,000 USDT, 12 bps per unit traded.

| | Final equity | CAGR | Max drawdown | 2022 | Admission |
|---|---|---|---|---|---|
| **B1** v54 long/flat, 10 coins | 116,360 | 50.5% | 54.4% | −19% | not admitted: drawdown above 52.1% (2/3 of 78.1%) |
| 10-coin buy-and-hold | 154,129 | 57.8% | 78.1% | −65% | |
| **B2** BTC/ETH above SMA200 | 130,291 | 53.4% | 50.5% | −8% | **admitted** (all five) |
| BTC/ETH buy-and-hold | 174,062 | 61.0% | 77.8% | −67% | |

- 2020–25 contains one of the strongest bull runs on record; CAGRs are not
  expectations. What carries over is the shape: B2 gave up some upside (2020
  +152% against +382%) and avoided most of 2022.
- B2's largest drawdown (−51%, 2021-05-11 to 07-23) came from the May 2021 crash,
  while both coins were still above their averages. The filter protects against
  long bear markets, not fast crashes.
- B1 missed by 2.3 points and is not rescued.

### Sizing under ADR-015 (exploratory, after admission)

At full exposure B2 had 70 days with a daily loss of 5% or more (about 11 a
year), each of which stops trading under ADR-001 and ADR-015. Holding units
without rebalancing also lets exposure drift up in rallies, so a reduced
exposure needs a scheduled reset. With weekly rebalancing to a fraction of the
B2 target, against buy-and-hold scaled and rebalanced the same way:

| Exposure | Days ≤ −5% | Worst day | Max drawdown | CAGR | 2022 |
|---|---|---|---|---|---|
| B2 × 1.0 | 68 | −22.1% | 49% | 51% | −8% |
| B2 × 0.5 | 10 | −11.0% | 27% | 27% | −4% |
| **B2 × 0.4** | 4 | −8.8% | 22% | 22% | −3% |
| B2 × 0.3 | 3 | −6.6% | 17% | 16% | −2% |
| Buy-and-hold × 0.4 | 7 | | 41% | 28% | −31% |
| Buy-and-hold × 0.3 | 3 | | 32% | 21% | −23% |

Accepted for paper: B2 at 40% exposure (20% per coin), rebalanced weekly and on
every signal change, as `rule_beta_sma200_v1`.

### Nautilus verification (2026-10-20)

`BaselineNautilusStrategy` sizes a position as a fraction of marked equity and
resets it weekly (`--target-equity-fraction 0.4 --rebalance-weekday 6`). One run
per coin, 10,000 USDT each, 1-hour bars, Binance taker fee 0.1%, against
`apps.research.beta.simulate` with the same settings:

| Coin | Nautilus final | Reference final | Max drawdown (Nautilus / ref) | Days held |
|---|---|---|---|---|
| BTC | 24,324 | 24,369 (−0.18%) | 33.1% / 31.4% | 1,396 / 1,396 |
| ETH | 40,417 | 41,263 (−2.05%) | 31.6% / 32.7% | 1,366 / 1,366 |

Daily equity differs by 0.8–0.9% at the median (fills one hour after the daily
close, lot rounding, skipped sub-10-USDT resets). Two such sleeves of half the
capital each behave like one account at 20% per coin (max drawdown 22.5% against
21.9%), so one runner per coin is an acceptable deployment.

## 6. What this ADR does not do

- Does not change ADR-014 or reopen any rejected identity.
- Does not authorize testnet keys, real money or perpetuals.
- Does not add services or data sources beyond Binance public archives.
