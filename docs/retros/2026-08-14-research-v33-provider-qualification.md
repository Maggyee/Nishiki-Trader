# 2026-08-14 Protocol v33 Provider Qualification

- **Status**: fully provider qualified; development PnL sealed.
- **Mechanisms**: Cboe Implied Correlation Term Structure relief (COR3M, COR6M, COR1Y).
- **Development**: 2020-01-01 through 2022-12-31; unopened.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Provider outcome

From freeze commit `b3bb93a`, all three pre-registered Cboe implied correlation term structure indices were requested once via HTTP GET and fully qualified under the frozen coverage gates:

1. `COR3M`: 755 development observations (2020-01-02 to 2022-12-30), 41 warmup rows, schema OHLC (`CLOSE`), maximum calendar gap 4 days.
2. `COR6M`: 756 development observations (2020-01-02 to 2022-12-30), 41 warmup rows, schema OHLC (`CLOSE`), maximum calendar gap 4 days.
3. `COR1Y`: 756 development observations (2020-01-02 to 2022-12-30), 41 warmup rows, schema OHLC (`CLOSE`), maximum calendar gap 4 days.

No values were forward-filled or interpolated, and no historical vintage claim is made. Development factor CSV files were extracted point-in-time and verified against immutable raw snapshots.

Development signals and strategy-specific PnL remain unopened until this provider qualification is committed.
