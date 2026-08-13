# 2026-08-13 Protocol v28 Provider Qualification

- **Status**: all three identities provider-rejected; protocol closed.
- **Pre-data commit**: `d425a3c` on `origin/main`.
- **Signals/PnL**: unopened.
- **Trading effect**: none.

Each locked DefiLlama options-volume or open-interest URL was opened exactly
once from the freeze HEAD. Options notional and options premium each have only
414 development observations versus 700 required. Perpetual DEX open interest
has 675 versus 700. No snapshot or factor was written, and retry is forbidden.

Zero candidates may generate signals or PnL. Confirmation remains sealed. This
qualification does not alter SourcePolicy, existing paper shadow, testnet, live
trading, or the future blind. Any later options or open-interest study needs a
new identity with a different coverage contract.
