# Phase 2 Research Protocol v25

- **Status**: pre-registered; DefiLlama TVL JSON bodies sealed.
- **Mechanisms**: DefiLlama historical chain TVL expansion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v25 does not retune Cboe implied volatility, option-surface shape, OFR stress,
FRED liquidity, Wikipedia pageviews, Fear and Greed labels, or Coin Metrics
stablecoin-supply / network series. It asks whether capital locked in DeFi,
measured by DefiLlama historical chain TVL excluding liquid staking and
double-counted TVL, expanding over five official daily observations precedes
BTC risk-on demand.

The three locked series are all-chain TVL, Ethereum-chain TVL, and
Bitcoin-chain TVL. Each rule buys BTCUSDT Spot only when the latest completed
TVL minus the value five official observations earlier is strictly positive;
otherwise it is flat. There is no sign flip, lookback grid, ensemble, or
post-result reparameterization.

TVL history is a current reconstruction, not a vintage tape. Decisions wait
two calendar days after the UTC observation date. Endpoints have no start/end
filter, so one current-history GET per kind is allowed; rows after 2022-12-31
are counted, not used for development factors, signals, or PnL.

## Gates and progression

Unchanged development gates. A development passer may only enter a separately
frozen 2023-2025 confirmation contract. Existing paper-shadow collectors,
SourcePolicy, testnet, live trading, and the future blind stay untouched.
