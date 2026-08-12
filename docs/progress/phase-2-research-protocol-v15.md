# Phase 2 Research Protocol v15

- **Frozen**: 2026-08-12 before opening the FRED CSV body.
- **Status**: blocked at FRED provider qualification; development values unopened.
- **Trading effect**: none.

V15 locks three U.S. rate mechanisms: falling 10-year real yields, steepening
10y-minus-2y Treasury slope, and falling realized volatility of the 10-year
nominal yield. These represent discount-rate relief, improving growth/liquidity
expectations, and reduced rate uncertainty respectively.

The credential-free combined CSV request returned HTTP 200 to HEAD without a
body. FRED documents all three series as daily: `DFII10` and `DGS10` originate
from the Federal Reserve H.15 release, while `T10Y2Y` is calculated from
Treasury constant-maturity series. The exact request, fields, signs, and
lookbacks are frozen before development values.

No missing rate is filled. Only dates with all three numeric observations are
eligible, and each observation is delayed four calendar days to conservatively
cover next-business-day publication across weekends and holidays. Present-day
CSV history is reconstruction evidence, not a historical FRED-vintage claim.

The existing 2020-2022 cost, breadth, activity, concentration, lineage,
downtime, and duplicate-replay gates apply. The 2023-2025 confirmation remains
sealed until a development candidate passes every gate. V12-v14, GVZ paper
shadow, SourcePolicy, testnet, live trading, and the shared future blind are
unchanged.

## Provider outcome

The one allowed GET was opened from clean pushed commit `91a79e1`. FRED did
not return response headers or body within the locked 30-second client timeout.
No CSV row or factor value was received. This reproduces the direct-CSV
availability weakness previously seen in Protocol v4, so v15 stops at
`blocked_provider_qualification` rather than retrying until one response works.

Development, confirmation, signals, and PnL remain unopened. A direct U.S.
Treasury annual CSV route may be evaluated only under a separately frozen
provider identity.
