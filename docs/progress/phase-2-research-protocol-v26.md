# Phase 2 Research Protocol v26

- **Status**: pre-registered; DefiLlama DEX volume JSON bodies sealed.
- **Mechanisms**: DefiLlama aggregated DEX daily-volume expansion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v26 does not retune DefiLlama TVL expansion or any rejected Cboe, OFR, FRED,
Wikipedia, Fear and Greed, or Coin Metrics identity. It asks whether rising
on-chain DEX trading activity, measured by DefiLlama aggregated daily DEX
volume, precedes BTC risk-on demand.

The three locked series are all-DEX volume, Ethereum-chain DEX volume, and
Solana-chain DEX volume. Each rule buys BTCUSDT Spot only when the latest
completed daily volume minus the value five official observations earlier is
strictly positive; otherwise it is flat. There is no sign flip, lookback grid,
ensemble, or post-result reparameterization.

Volume history is a current reconstruction, not a vintage tape. Decisions wait
two calendar days after the UTC observation date. One current-history GET per
kind is allowed; rows after 2022-12-31 are counted, not used for development
factors, signals, or PnL.

The frozen chart schema is an object whose `totalDataChart` is a list of
`[unix_seconds, volume]` pairs at UTC midnight. A schema mismatch rejects that
kind without retry.

## Gates and progression

Unchanged development gates. A development passer may only enter a separately
frozen 2023-2025 confirmation contract. Existing paper-shadow collectors,
SourcePolicy, testnet, live trading, and the future blind stay untouched.
