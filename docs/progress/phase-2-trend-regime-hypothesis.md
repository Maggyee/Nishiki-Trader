# Phase 2 Trend-Regime Hypothesis

- **Status**: Locked before reading 2025 market data
- **Locked on**: 2026-07-10
- **Source/model**: `rule_trend_regime_v1 / ema24-96-1h-mom24-atr14x0.5-v1`
- **Blind window**: 2025-08-01 00:00 through 2025-12-31 23:59 UTC
- **Policy effect**: None; backtest research only

## Economic hypothesis

The rejected 15-minute breakout candidate traded too frequently and lost even
before modeled costs. The next hypothesis is that BTC Spot multi-day momentum
persists only when a medium-term trend and price displacement agree. Moving to
one-hour bars should reduce churn enough that a 24 bps modeled round trip is no
longer the dominant result driver.

The fingerprint is fixed as follows:

- Deterministically resample BTCUSDT 1m OHLCV to 1h bars.
- Fast/slow trend: EMA(24) and EMA(96).
- Momentum confirmation: 24-bar close return must be positive for entry.
- Volatility buffer: ATR(14) × 0.5 around the slow EMA.
- Enter long when fast EMA is above slow EMA, close is above slow EMA plus the
  ATR buffer, and 24h momentum is positive.
- Exit to flat when fast EMA falls below slow EMA or close falls below slow EMA
  minus the ATR buffer.
- Emit only state transitions; never emit `sell` or target a short position.
- TTL is 3600 seconds. No parameter search or threshold sweep is allowed under
  this model version.

## Blind review protocol

The 2024 data may be used only as implementation/warm-up context. No 2025 bar
or result was read before this fingerprint and window were written.

After committing this file and the generator:

1. Run a clean development screen on the already-opened 2024-08..2024-12
   window. Continue only if gross, base, and stress aggregate PnL are all
   positive, the source stays long/flat, and sidecars reproduce. This screen
   cannot qualify the source for paper; it only decides whether to spend the
   untouched 2025 blind window.
2. If the development screen passes, import Binance public BTCUSDT 1m data
   through 2025-12-31. Binance's official
   public-data documentation states that Spot archive timestamps use
   microseconds from 2025-01-01, so the importer must detect ms/us precision.
3. Generate the fixed signal stream once and run two independent
   NautilusTrader CASH/NETTING backtests on the locked five-month window.
4. Run `alpha.review.v1` with gross, base (10 + 2 bps), and stress (10 + 5 bps)
   per-fill scenarios plus the same-size buy-and-hold reference.
5. Require base and stress net PnL > 0, at least 4/5 base-positive months, at
   least 30 closed positions, zero shorts/blockers, and byte-reproducible
   sidecars. No gate is weakened for a low-turnover strategy.

If the candidate fails, do not tune this fingerprint against the opened blind
window. If it passes profitability but has fewer than 30 positions, record
`insufficient_evidence` and do not enter paper_shadow.
