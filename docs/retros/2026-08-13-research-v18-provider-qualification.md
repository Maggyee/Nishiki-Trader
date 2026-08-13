# 2026-08-13 Protocol v18 Provider Qualification

- **Status**: qualified; development PnL unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v18 was committed and pushed at `77afac1` before any OHLC CSV body
was opened. Each official Cboe history was fetched once and independently
re-verified:

| Index | Reserve rows | Reserve window | Snapshot |
|---|---:|---|---|
| VXEEM | 755 | 2020-01-02 .. 2022-12-30 | `sha256:c48245b4…6bd08a` |
| VXEFA | 755 | 2020-01-02 .. 2022-12-30 | `sha256:b180b9e0…463ec12` |
| VXN | 758 | 2020-01-02 .. 2022-12-30 | `sha256:7a92d571…de0d84d1` |

All three files use the locked `DATE,OPEN,HIGH,LOW,CLOSE` header, contain no
forward fill, and cover the development reserve. No factor CSV export, SignalEvent
generation, Nautilus replay, or PnL was opened. v17 remains closed. v8/v16 paper
shadow, SourcePolicy, testnet, and live paths are unchanged.

The next permitted step is a committed development review of the frozen
five-observation rules on 2020-2022, without retuning.
