# Phase 2 Research Protocol v22

- **Status**: provider qualification complete; SKEW/COR1M qualified, DSPX rejected, development PnL sealed.
- **Mechanisms**: tail skew, implied correlation, and implied dispersion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31, sealed.
- **Future blind**: sealed.

## Independent hypotheses

Prior Cboe studies used the level change of an implied-volatility index for a
single underlier. v22 instead asks whether the option surface's cross-sectional
shape contains a risk-regime signal for BTC:

1. falling `SKEW` means the price of equity left-tail asymmetry is easing;
2. falling `COR1M` means expected equity co-movement and systemic clustering
   are easing;
3. rising `DSPX` means idiosyncratic movement is becoming larger relative to
   market-wide co-movement, a diversification/risk-on state.

Every rule uses exactly the latest value minus the value five official
observations earlier. The first two buy only on a negative change; DSPX buys
only on a positive change. All begin flat and emit only state changes. There
is no threshold/lookback grid, alternate sign, ensemble, or post-result
reparameterization.

## Provider and point-in-time boundary

Official Cboe product/methodology pages were opened to establish definitions
and history availability. No historical CSV body was opened. The provider
contract freezes one credential-free history URL per index and accepts only
the two documented Cboe history layouts already encountered in this project:
`DATE,<INDEX>` or `DATE,OPEN,HIGH,LOW,CLOSE`; the latter uses only `CLOSE`.

Each kind gets one request and no retry. Qualification is independent, so a
schema or coverage failure rejects that kind without preventing the remaining
pre-registered requests. Decisions occur one calendar day after the official
observation. There is no fill/interpolation and no historical-vintage claim.

## Gates and progression

The frozen gates remain base/stress PnL above zero, at least two positive
years, 18 positive months, 30 closed positions, positive leave-best base PnL,
and two identical clean replays. A development survivor may only enter a new
committed confirmation contract. A confirmed survivor may only become
eligible for a separate ADR-007 `paper_shadow` review; no policy, testnet,
live path, or future blind changes here.

## Provider outcome

The pre-data contract was pushed at `ee4bbe3`. SKEW and COR1M each qualify on
756 development observations, 41 warmup observations, and a maximum four-day
gap with no fill or interpolation. DSPX violates the frozen positive-value
contract and is rejected without snapshot, factor, retry, signal, or PnL.

The qualified snapshot and factor hashes are in
`docs/progress/phase-2-research-v22-provider-qualification.json`. SKEW and
COR1M development PnL stays sealed until this qualification is committed and
pushed.
