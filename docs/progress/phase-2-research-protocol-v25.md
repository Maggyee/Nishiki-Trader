# Phase 2 Research Protocol v25

- **Status**: closed; Bitcoin provider-rejected, Ethereum development-rejected, all-chain TVL failed confirmation.
- **Mechanisms**: DefiLlama historical chain TVL expansion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31, complete; identity rejected.
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

## Development outcome

Two clean replays per qualified candidate from `e4b22c0` reproduce with
identical fills and no evidence blockers. Ethereum TVL expansion is rejected
at 15/36 positive months and negative leave-best base PnL. Bitcoin-chain TVL
was never replayed.

All-chain TVL expansion passes every frozen gate: gross/base/stress
+30.655530/+24.445097/+22.892488 USDT, 2/3 years and 19/36 months are
positive, 94 positions, and +9.220236 leave-best base PnL. Confirmation values
remain sealed until a separate contract is frozen. That contract must reuse
the already-captured all-chain snapshot without a new GET.

## Confirmation freeze

The unchanged all-chain identity is locked in
`docs/progress/phase-2-research-v25-confirmation.json` against development
review `342a0e3`. Confirmation values, returns, and PnL stay unopened until
this freeze is on `origin/main`. No new DefiLlama GET is allowed; post-2025
rows in the captured snapshot are counted and ignored. Ethereum and Bitcoin
identities stay closed.

## Confirmation outcome

Two clean replays from `0bb16d3` reproduce with identical fills and no
evidence blockers. All-chain TVL expansion is rejected on 2023-2025:
gross/base/stress +27.949010/+9.738210/+5.185511 USDT, 2/3 years, 14/36
months versus 18 required, 115 positions, and -12.753346 leave-best base PnL.
It cannot enter ADR-007 or `paper_shadow`. Do not retune this identity.
