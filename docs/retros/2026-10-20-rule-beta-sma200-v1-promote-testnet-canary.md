# Promotion review — rule_beta_sma200_v1 / btc-eth-sma200-v1

- **Date (UTC)**: 2026-10-20
- **Operator**: nishiki
- **Decision**: PROMOTE
- **Decision allowed by gates**: yes

Written by hand under [ADR-019](../decisions/019-beta-allocation.md) §4:
`promotion_review` only accepts paper or testnet bundles, and the operator chose
the Spot testnet instead of the local paper runner ("按你说的做", 2026-10-20).
The gates are ADR-019 §3 (beta track, no alpha claim), not ADR-014.

## 1. Source / model

- source: `rule_beta_sma200_v1`
- model_version: `btc-eth-sma200-v1`

## 2. Current vs target policy

- current_stage: `backtest_baseline`
- target_stage: `testnet_canary`
- target_policy: dry_run=False, position_pct_multiplier=0.2 (ADR-008 §6.6 cap), min_confidence_override=None
- sizing: target_equity_fraction 0.4, weekly reset after Sunday, allocated capital 5,000 USDT per coin;
  with the 0.2 multiplier a position is 400 USDT per coin

## 3. Evidence

- ADR-019 §3 admission, criteria committed before the run (ed22394): B2 passed all five
  ([results/beta-2026-10.json](../research/results/beta-2026-10.json)).
- Nautilus verification (ADR-019 §5): backtest bundles
  `data/backtests/20261020-132723Z-8b83bbbb` (BTC) and `data/backtests/20261020-132729Z-9d4bd489`
  (ETH) end within 2% of the reference with identical holding days.
- Signals: `apps/strategies_freqtrade/beta_signals.py`, same rule and encoding as the backtest.

## 4. Conditions

- Testnet only, at least four weeks, including 14 consecutive days without manual
  intervention. Any real-money step is a separate operator decision (ADR-019 §2.3, ADR-013).
- The runner's auto-flatten triggers stay armed (daily loss 5% of 10,000 USDT, exchange
  error and reconnect bursts). A drawdown beyond the historical maximum stops the test
  for an operator review.
