# 2026-08-13 Protocol v17 Provider Qualification

- **Status**: blocked before factor values.
- **Development PnL**: unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v17 was committed and pushed at `c0a9629` before any Cboe CSV body
was opened. The one allowed VXEEM GET returned UTF-8 CSV whose header was
`DATE,OPEN,HIGH,LOW,CLOSE`, not the frozen `DATE,VXEEM`. Parsing stopped at
the header comparison. No close value, reserve count, signal, or PnL was
produced. VXEFA and VXN were not fetched.

The protocol is closed as `blocked_provider_qualification`. It will not rewrite
the locked columns, reuse this identity, or treat the observed header as a
signal input. An OHLC recovery requires a new protocol identity frozen before
the next body access.
