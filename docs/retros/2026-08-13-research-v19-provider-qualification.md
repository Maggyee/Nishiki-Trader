# 2026-08-13 Protocol v19 Provider Qualification

- **Status**: RVX and VXD qualified; VXFXI rejected on coverage.
- **Development PnL**: unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v19 was committed and present on `origin/main` at `a2ea80a` before
any CSV body was opened. Body-free HEAD checks returned HTTP 200 and
`text/csv` for all three official endpoints. Each body was then requested
exactly once.

| Index | Result | Development rows | Development window | Snapshot |
|---|---|---:|---|---|
| RVX | qualified | 755 | 2020-01-02 .. 2022-12-30 | `sha256:c2179bee…cf08dc` |
| VXD | qualified | 758 | 2020-01-02 .. 2022-12-30 | `sha256:6161821e…40bc04` |
| VXFXI | provider reject | 533 | below locked 700-row minimum | none |

RVX and VXD use the locked `DATE,OPEN,HIGH,LOW,CLOSE` header, contain no
forward fill, and cover the frozen development reserve. Their immutable raw
envelopes re-verify independently.

The sole VXFXI response also matched the header but supplied only 533 rows in
2020-2022. Parsing failed at the pre-registered 700-row coverage gate before
an envelope was written. It will not be fetched again, filled, thresholded,
or sent to a backtest. This is a data rejection, not a profitable/unprofitable
strategy result.

After this qualification result is committed and pushed, only the unchanged
RVX and VXD identities may export factors and enter duplicate development
replays. The locked candidate count remains three; VXFXI is carried into the
review as a provider-rejected candidate. No factor value, SignalEvent, PnL,
confirmation row, or future-blind row was opened during qualification.
