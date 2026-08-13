# 2026-08-13 Protocol v32 Provider Qualification

- **Status**: BPVIX qualified; EUVIX and JYVIX rejected because the 2020-2022
  reserve ends too early.
- **Pre-data commit**: `89a9a9c` on `origin/main`.
- **Development PnL**: unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v32 was committed and present on `origin/main` at `89a9a9c` before
any CSV body was opened. Each locked Cboe history URL was then requested
exactly once.

| Index | Result | Notes |
|---|---|---|
| EUVIX | provider reject | development last date before 2022-12-29; no snapshot |
| JYVIX | provider reject | development last date before 2022-12-29; no snapshot |
| BPVIX | qualified | 754 unfilled 2020-01-02 .. 2022-12-30 rows; `sha256:71cb6090…00d30a` |

BPVIX uses the locked scalar `DATE,BPVIX` header, contains no forward fill,
and covers the frozen development reserve. The immutable raw envelope
re-verifies independently. Development factors stop at 2022-12-30.

EUVIX and JYVIX failed the pre-registered last-observation gate before an
envelope was written. They will not be fetched again, filled, or sent to a
backtest. This is a data rejection, not a strategy PnL result.

After this qualification result is committed and pushed, only the unchanged
Pound FX vol-relief identity may export 2020-2022 signals and enter duplicate
development replays. Confirmation remains sealed.
