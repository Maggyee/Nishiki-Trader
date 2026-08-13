# Phase 2 Research Protocol v28

- **Status**: pre-registered; DefiLlama options-volume and open-interest JSON bodies sealed.
- **Mechanisms**: DefiLlama aggregated options notional volume, options premium volume, and perpetual DEX open-interest expansion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v28 does not retune DefiLlama TVL, spot DEX volume, or protocol fees, and it
does not reopen Cboe option-surface or volatility identities. It asks whether
rising on-chain options activity or perpetual DEX open interest precedes BTC
risk-on demand.

The three locked series are all-chain options `dailyNotionalVolume`, options
`dailyPremiumVolume`, and perpetual DEX open interest. Each rule buys BTCUSDT
Spot only when the latest completed daily amount minus the value five official
observations earlier is strictly positive; otherwise it is flat. There is no
sign flip, lookback grid, ensemble, or post-result reparameterization.

These histories are current reconstructions, not vintage tapes. Decisions wait
two calendar days after the UTC observation date. One current-history GET per
kind is allowed; rows after 2022-12-31 are counted, not used for development
factors, signals, or PnL.

The frozen chart schema is an object whose `totalDataChart` is a list of
`[unix_seconds, amount]` pairs at UTC midnight. A schema mismatch rejects that
kind without retry.

## Gates and progression

Unchanged development gates. A development passer may only enter a separately
frozen 2023-2025 confirmation contract. Existing paper-shadow collectors,
SourcePolicy, testnet, live trading, and the future blind stay untouched.
