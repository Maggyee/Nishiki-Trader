# Phase 2 Research Protocol v21

- **Status**: pre-registered; historical CSV bodies, factor values, signals, and PnL unopened.
- **Mechanism**: U.S. dollar net-liquidity expansion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31, sealed.
- **Future blind**: sealed.

## Why this is independent

Protocol v21 does not change a failed v20 threshold or reuse an OFR stress
component. It tests a balance-sheet mechanism: Federal Reserve assets less the
Treasury General Account and overnight reverse repos. The candidate is
long/flat BTC Spot and assumes that a four-week expansion in this net dollar
liquidity measure is supportive for risk-asset demand.

The exact identity is
`rule_us_net_liquidity_expansion_v1 / fred-walcl-wdtgal-rrpontsyd-diff4w-positive-lag7d-v1`.
Net liquidity, in millions of dollars, is `WALCL - WDTGAL - 1000 *
RRPONTSYD`. Buy only when its change from four exact common weekly
observations earlier is strictly positive; otherwise stay flat. Begin flat and
emit only state changes. No alternate sign, lookback search, threshold grid,
ensemble, or post-result reparameterization is permitted.

## Point-in-time boundary

Official metadata pages were used to verify series meanings, units, frequency,
and the H.4.1 release schedule. Those pages exposed five August 2026 headline
values per series; they lie outside both historical partitions and are not
used. No FRED CSV body or 2019-2025 historical value was opened before this
contract.

The development collector may issue exactly one credential-free GET for each
of `WALCL`, `WDTGAL`, and `RRPONTSYD`, limited to 2019-10-01 through
2022-12-31. Series are joined only on exact observation dates. Every decision
is delayed seven calendar days, no value is filled or interpolated, and the
study makes no historical-vintage claim because FRED current history may be
revised.

## Gates and progression

The one candidate must be positive under base and stress costs, profitable in
at least two of three years and 18 of 36 months, close at least 30 positions,
remain positive after removing its best base-cost position, and reproduce in
two clean Nautilus cash-account replays. A development pass can open only a
separately committed 2023-2025 confirmation contract. A confirmation pass can
create only ADR-007 `paper_shadow` review eligibility; it cannot mutate policy,
resume testnet, touch live trading, or open the future blind.
