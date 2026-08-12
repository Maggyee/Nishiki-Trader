# 2026-08-12 Protocol v15 Provider Qualification

- **Status**: blocked before factor values.
- **Development PnL**: unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v15 was committed and pushed at `91a79e1` before its exact combined
FRED CSV request was opened. The only GET reached the 30-second read timeout
without response headers or a body. Consequently no rate value, signal,
Nautilus bundle, or PnL was produced.

The protocol is closed as `blocked_provider_qualification`. It will not retry
the same endpoint until a favorable response appears. The same economic
mechanisms may use the official U.S. Treasury annual CSV only under a distinct,
prospectively frozen provider contract.
