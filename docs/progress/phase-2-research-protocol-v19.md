# Phase 2 Research Protocol v19

- **Frozen**: 2026-08-13 before opening any v19 Cboe CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v19.json`
- **Provider contract**: `docs/progress/phase-2-research-v19-data-sources.json`
- **Status**: RVX/VXD provider-qualified; VXFXI coverage-rejected; development PnL sealed.
- **Trading effect**: none.

## Why this batch is allowed

The original 16-family stop rule remains binding. GVZ, Treasury-yield
volatility, and VXN paper-shadow collectors stay untouched. v19 does not
retune VIX, OVX, GVZ, VIX9D, VVIX, VXEEM, VXEFA, or VXN, combine them after
PnL, or open the shared future blind.

It locks three new Cboe underliers:

1. US small-cap implied volatility (`RVX`);
2. US Dow Jones implied volatility (`VXD`);
3. China large-cap ETF implied volatility (`VXFXI`).

BTC often trades as a high-beta risk asset. The claim is that relief in these
surfaces can spill into BTC demand without a BTC chart rule. The five-observation
negative-change form matches earlier Cboe relief tests, but every source, model,
URL, and index fingerprint is new.

SKEW remains excluded because of the announced methodology change. TYVIX/VXTLT
remain too close to the confirmed Treasury-volatility identity. VIX3M/VIX6M are
not used because they would retry SPX vol-level relief under a new tenor.

OHLC `CLOSE` is locked before body access because v17 failed closed on
`DATE,INDEX` and v18 observed `DATE,OPEN,HIGH,LOW,CLOSE`. A later schema
mismatch still fails closed.

## Locked candidates

All three target BTCUSDT Spot, emit only `buy`/`flat` on state changes, use a
one-day TTL and confidence 0.75, and start each scored period flat.

- `rule_russell_vol_relief_v1 / cboe-rvx-ohlc5obs-negative-1d-v1`
- `rule_dow_vol_relief_v1 / cboe-vxd-ohlc5obs-negative-1d-v1`
- `rule_china_vol_relief_v1 / cboe-vxfxi-ohlc5obs-negative-1d-v1`

Buy iff the latest completed close minus the close five official observations
earlier is strictly negative; otherwise flat. No sign flip, grid, or
PnL-selected ensemble.

## Evidence partitions and boundaries

The 2020-2022 development reserve, 2023-2025 confirmation seal, shared
2026-09..2027-01 future blind, costs, and gates are unchanged. v8/v16/v18
paper shadow, SourcePolicy, testnet, and live trading stay untouched.

The pre-access contract must be committed and pushed before any v19 CSV body
is downloaded. HEAD may qualify URLs without reading values. Each body may be
fetched once after that push.

## Provider outcome

From pushed commit `a2ea80a`, all three endpoints passed body-free HEAD and
were opened once. RVX and VXD qualified with 755 and 758 unfilled development
observations. VXFXI supplied only 533 observations against the frozen minimum
of 700, so it is provider-rejected without retry or backtest. See
`docs/retros/2026-08-13-research-v19-provider-qualification.md`.

After this outcome is committed, only RVX and VXD may enter duplicate
2020-2022 development replays. VXFXI remains the third locked candidate and is
reported as a data rejection. Confirmation and the future blind stay sealed.
