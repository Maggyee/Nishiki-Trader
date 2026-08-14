# 2026-08-14 Protocol v34 Provider Qualification

- **Status**: fully provider qualified; development PnL sealed.
- **Mechanisms**: Cboe Benchmark US Treasury Yield relief (FVX: 5-Year, TNX: 10-Year, TYX: 30-Year).
- **Development**: 2020-01-01 through 2022-12-31; unopened.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Provider outcome

From freeze commit `82516d2`, all three pre-registered Cboe benchmark Treasury yield series were requested once via HTTP GET and fully qualified under the frozen coverage gates:

1. `FVX`: 757 development observations (2020-01-02 to 2022-12-30), 41 warmup rows, schema scalar (`FVX`), maximum calendar gap 4 days.
2. `TNX`: 757 development observations (2020-01-02 to 2022-12-30), 41 warmup rows, schema scalar (`TNX`), maximum calendar gap 4 days.
3. `TYX`: 757 development observations (2020-01-02 to 2022-12-30), 41 warmup rows, schema scalar (`TYX`), maximum calendar gap 4 days.

No values were forward-filled or interpolated, and no historical vintage claim is made. Development factor CSV files were extracted point-in-time and verified against immutable raw snapshots.

Development signals and strategy-specific PnL remain unopened until this provider qualification is committed.
