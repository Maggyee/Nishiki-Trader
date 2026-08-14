# Phase 2 Alpha Research Protocol v36: Cboe Option Strategy & Variance Premium Expansion

- **Status**: pre-registered before reading CSV bodies.
- **Parent phase**: Phase 2 Non-Correlated Alpha Discovery.
- **Historical development window**: 2020-01-01 through 2022-12-31 (warmup from 2019-11-01).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Execution target**: `BTCUSDT.BINANCE` 1h Cash spot netting.
- **Live trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Candidates and Financial Logic

1. **`vpn_expansion`** (`rule_cboe_vpn_expansion_v1 / cboe-vpn-diff5-positive-lag1d-v1`):
   - Underlier: Cboe VIX Premium Strategy Index (`VPN`).
   - Economic logic: Tracks the systematic harvesting of the VIX variance risk premium (VRP) by selling 1-month VIX futures. Positive 5-observation return reflects smooth equity volatility contango, institutional short-volatility profitability, and steady macro liquidity expansion.
2. **`put_expansion`** (`rule_cboe_put_expansion_v1 / cboe-put-diff5-positive-lag1d-v1`):
   - Underlier: Cboe S&P 500 PutWrite Index (`PUT`).
   - Economic logic: Tracks the return on cash-secured put option writing on the S&P 500. A rising index indicates successful equity volatility risk premium collection with subdued tail crash risks.
3. **`bxm_expansion`** (`rule_cboe_bxm_expansion_v1 / cboe-bxm-diff5-positive-lag1d-v1`):
   - Underlier: Cboe S&P 500 BuyWrite Index (`BXM`).
   - Economic logic: Tracks covered call option writing against the S&P 500. Positive 5-day change indicates healthy equity accumulation and manageable equity volatility.

## Point-in-Time Contract

- Publication lag: 1 calendar day ($D+1$).
- Warmup: 2019-11-01 to 2019-12-31.
- Signal rule: $1_{\Delta_5(\text{Index}) > 0.0}$, long spot when positive, flat otherwise.
