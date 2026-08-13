# 2026-08-13 Protocol v20 OFR Provider Qualification

- **Status**: provider qualified; development PnL unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v20 was committed and pushed at `5d3a899` before the official OFR
FSI JSON body was opened. The single allowed GET was retained byte-for-byte in
an immutable local envelope and independently re-verified.

The required `OFRFSI`, `Credit`, and `Flight_to_Safety` objects each contain
6,733 observations and share exactly the same timestamps. The frozen
development reserve qualifies with 762 unfilled observations from 2020-01-02
through 2022-12-30, a maximum four-calendar-day gap, and 41 warmup rows.

No factor value was reported, SignalEvent generated, return calculated, or
PnL opened during qualification. The response is a current-history snapshot,
not historical publication vintages. The D+5 reconstruction and forward
revision fail-close limitation remain binding.

After this result is committed and pushed, all three unchanged candidates may
enter duplicate 2020-2022 development replays. Confirmation and the future
blind remain sealed.
