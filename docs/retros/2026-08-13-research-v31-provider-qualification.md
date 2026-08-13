# 2026-08-13 Protocol v31 Provider Qualification

- **Status**: VXTLT qualified; VXSLV and VXXLE rejected on coverage.
- **Pre-data commit**: `8f22da9` on `origin/main`.
- **Development PnL**: unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v31 was committed and present on `origin/main` at `8f22da9` before
any CSV body was opened. Each locked Cboe history URL was then requested
exactly once.

| Index | Result | Development rows | Development window | Snapshot |
|---|---|---:|---|---|
| VXSLV | provider reject | 533 | below locked 700-row minimum | none |
| VXXLE | provider reject | 533 | below locked 700-row minimum | none |
| VXTLT | qualified | 755 | 2020-01-02 .. 2022-12-30 | `sha256:5944a52b…ce917e` |

VXTLT uses the locked scalar `DATE,VXTLT` header, contains no forward fill,
and covers the frozen development reserve. The immutable raw envelope
re-verifies independently. Development factors stop at 2022-12-30.

VXSLV and VXXLE matched an accepted header but supplied only 533 rows in
2020-2022. Parsing failed at the pre-registered 700-row coverage gate before
an envelope was written. They will not be fetched again, filled, thresholded,
or sent to a backtest. This is a data rejection, not a strategy PnL result.

After this qualification result is committed and pushed, only the unchanged
long-Treasury ETF vol-relief identity may export 2020-2022 signals and enter
duplicate development replays. The locked candidate count remains three;
VXSLV and VXXLE are carried as provider-rejected candidates. No SignalEvent,
PnL, confirmation row, or future-blind row was opened during qualification.
