# Phase 2 Research Protocol v18

- **Frozen**: 2026-08-13 before opening any v18 Cboe CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v18.json`
- **Provider contract**: `docs/progress/phase-2-research-v18-data-sources.json`
- **Confirmation contract**: `docs/progress/phase-2-research-v18-confirmation.json`
- **Status**: VXN is `hold @ paper_shadow`; Day 1 qualified; weekday 03:30 UTC crontab installed.
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

Only that unchanged VXN identity may open 2023-2025. The development review
was committed at `98a0ef2` before the VXN-only confirmation contract was
frozen.

## Confirmation boundary

The confirmation contract locks the existing qualified VXN snapshot, OHLC
`CLOSE`, one-calendar-day availability lag, five-observation rule, flat fold
initial state, unchanged costs, 36-month breadth gates, duplicate replays, and
the already-audited v8 BTC execution catalog. It makes no new network request.

The contract and its factor/review code must be committed and pushed before
2023-2025 value rows are exported. Passing confirmation creates only
ADR-007 `paper_shadow` review eligibility. It cannot mutate SourcePolicy,
authorize paper simulation/testnet/live trading, or open the future blind.

## Confirmation data outcome

The locked snapshot supplies 752 unfilled confirmation observations: 250 in
2023, 252 in 2024, and 250 in 2025. Coverage runs from 2023-01-03 through
2025-12-31 with a maximum four-calendar-day gap. Forty-two late-2022 rows are
used only as indicator warmup. Export used no network request, forward fill,
return calculation, or future-blind access. The unchanged rule emits 144
confirmation signals; PnL remains unopened until this qualification is
committed and pushed.

## Confirmation outcome

Two clean Nautilus replays from pushed commit `9360eb3` have identical fills.
The unchanged VXN rule passes every frozen 2023-2025 gate: gross/base/stress
PnL is +70.753350/+60.207790/+57.571400 USDT, all three years and 20/36 months
are positive, 72 positions close, and leave-best base PnL remains +35.304076
USDT. There are zero shorts, effective blockers, or events in the one verified
exchange-unavailable hour.

This result permits a separate identity-specific ADR-007 `paper_shadow`
policy review only. It does not itself mutate SourcePolicy, authorize orders,
start a collector, resume testnet/live trading, or open the future blind.

## ADR-007 paper-shadow decision

The separate policy review records `hold @ paper_shadow` under
`SourcePolicy(dry_run=True, position_pct_multiplier=0.2,
min_confidence_override=None)`. A clean catalog-shadow bundle accepts all
129 in-window signals on the longest contiguous suffix, classifies all 129 as
dry run, and produces zero orders/fills, lag events, data gaps, kill-switches,
or review blockers.

This is the usable monitoring stage for the strategy, not return evidence and
not an execution authorization. Day 1 qualified from pushed commit `e90799e`
with a one-day-old official VXN close through 2026-08-12, 167 contiguous
closed BTC hours, 41 baseline signals, and zero new forward signals. The
operator-approved weekday 03:30 UTC crontab is installed once. Forward
progress is 1/7 qualified days and 0/50 new signals. `paper_simulated`,
testnet/live trading, and the future blind remain closed.
