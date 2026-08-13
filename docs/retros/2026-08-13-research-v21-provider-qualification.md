# 2026-08-13 Protocol v21 Provider Qualification

- **Status**: `blocked_provider_qualification`.
- **Pre-data commit**: `d9ec0e3` on `origin/main`.
- **Historical factor values**: none opened.
- **Signals/PnL**: none generated or opened.
- **Trading effect**: none.

Protocol v21 froze one U.S. net-liquidity rule and exactly three FRED CSV
requests before historical data access. The first allowed request, for
`WALCL`, waited 30 seconds and raised `TimeoutError` before response headers or
body arrived. The sequential collector therefore never attempted `WDTGAL` or
`RRPONTSYD` and wrote no snapshot, factor file, signal, or PnL.

The provider contract says any request failure closes qualification without a
retry, substitute provider, filling, or strategy evaluation. Accordingly v21
is closed. Its four-week rule was never tested and is neither accepted nor
rejected as alpha; the data route, not the strategy, is blocked.

Any later liquidity study requires a new provider identity frozen before data
access. It may not retry these FRED requests under v21 or infer performance
from the August 2026 metadata values. Existing paper-shadow policies, testnet,
live trading, and the future blind remain unchanged.
