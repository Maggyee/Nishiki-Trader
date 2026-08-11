# 2026-08-11 Research Protocol v7 Schema Qualification

- **Status**: fail-closed probe complete; schema-only correction locked.
- **Pre-access commit**: `799fd99` pushed to `origin/main`.
- **PnL accessed**: no.
- **Trading effect**: none.

The first official Cboe requests were made only after the pre-registration,
collector, generators, and tests were committed and pushed. All three bodies
failed before snapshot creation:

- VIX matched the locked OHLC header but an old row outside the registered
  2019-11 through 2022-12 factor window violated OHLC bounds.
- OVX returned the official close-only header `DATE,OVX`.
- GVZ returned the official close-only header `DATE,GVZ`.

No file was written and no factor, signal, BTC return, Nautilus run, policy,
credential, testnet, or live path was opened. The correction changes only the
provider schema contract: OVX/GVZ now lock their single value columns, and VIX
OHLC bounds are enforced on the exact warm-up/replication window consumed by
the candidate. Dates, candidate identities, five-observation rule, sign,
costs, gates, reserve, and future blind are unchanged.

The corrected contract and tests must be committed and pushed before retrying
any Cboe request.
