# Phase 2 Research Protocol v18

- **Frozen**: 2026-08-13 before opening any v18 Cboe CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v18.json`
- **Provider contract**: `docs/progress/phase-2-research-v18-data-sources.json`
- **Status**: development complete; Nasdaq vol relief is confirmation-eligible; confirmation sealed.
- **Trading effect**: none.

## Why this recovery is separate

Protocol v17 remains immutable. Its one allowed VXEEM GET failed closed because
the official header was `DATE,OPEN,HIGH,LOW,CLOSE` rather than `DATE,VXEEM`.
No close value was audited, and VXEFA/VXN were not fetched.

v18 keeps the same three economic rules and five-observation negative-change
threshold, but assigns new source/model fingerprints and locks the OHLC layout
before the next body access. v17 is not retried.

The VXEEM header was seen without values. VXEFA and VXN are locked to the same
OHLC CLOSE layout by analogy with VIX and the failed-closed VXEEM file, not
because their bodies were opened. A later schema mismatch still fails closed.

## Locked candidates

All three target BTCUSDT Spot, emit only `buy`/`flat` on state changes, use a
one-day TTL and confidence 0.75, and start each scored period flat.

- `rule_em_vol_relief_v2 / cboe-vxeem-ohlc5obs-negative-1d-v1`
- `rule_eafe_vol_relief_v2 / cboe-vxefa-ohlc5obs-negative-1d-v1`
- `rule_nasdaq_vol_relief_v2 / cboe-vxn-ohlc5obs-negative-1d-v1`

Buy iff the latest completed close minus the close five official observations
earlier is strictly negative; otherwise flat. No sign flip, grid, or
PnL-selected ensemble.

## Evidence partitions and boundaries

The 2020-2022 development reserve, 2023-2025 confirmation seal, shared
2026-09..2027-01 future blind, costs, and gates are unchanged from v17. v8 and
v16 paper shadow, SourcePolicy, testnet, and live trading stay untouched.

The pre-access contract must be committed and pushed before any v18 CSV body
is downloaded.

## Provider outcome

All three OHLC histories qualified from clean pushed commit `77afac1`. Reserve
coverage is 755/755/758 unfilled observations for VXEEM/VXEFA/VXN through
2022-12-30. No signal or PnL was opened. See
`docs/retros/2026-08-13-research-v18-provider-qualification.md`.

## Development outcome

Clean-commit duplicate replays from `a4ff746` are complete. VXEEM and VXEFA
are cost-negative and rejected. Nasdaq-100 five-observation relief passes
every frozen gate: base/stress +14.128562/+12.631995 USDT, 2/3 years, 21/36
months, 81 positions, and +3.151905 leave-best base PnL. Duplicate fills
match with zero shorts, blockers, or verified no-kline event hits.

Only that unchanged VXN identity may open 2023-2025, and only after this
review is committed. Confirmation, the future blind, and every trading path
remain closed.
