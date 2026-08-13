# Phase 2 Research Protocol v17

- **Frozen**: 2026-08-13 before reading any VXEEM, VXEFA, or VXN CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v17.json`
- **Provider contract**: `docs/progress/phase-2-research-v17-data-sources.json`
- **Status**: blocked at provider qualification; CSV schema mismatch; development values unopened.
- **Trading effect**: none.

## Why this batch is allowed

The original 16-family stop rule remains binding. Protocol v7 tested US equity,
energy, and gold implied-volatility relief; v9 tested the VIX curve and VVIX.
Those identities stay frozen. v17 does not retune them, combine them after PnL,
or open the shared future blind.

It locks three new Cboe underliers that describe different risk geographies and
styles:

1. emerging-market equity implied volatility (`VXEEM`);
2. developed international / EAFE implied volatility (`VXEFA`);
3. US Nasdaq-100 implied volatility (`VXN`).

BTC often trades as a high-beta risk asset. The economic claim is that relief
in these implied-vol surfaces can spill into BTC demand without using a BTC
chart rule. The structural form matches the frozen v7 five-observation negative
change, but every source, model, URL, and index fingerprint is new.

Rejected before lock: Cboe put/call CDN files last-modified 2020-10-30 (too
stale for 2020-2022), Fed H.10 historical text (404), EIA WTI (503), and
TYVIX/VXTLT (too close to the confirmed v16 Treasury-yield volatility identity).
A Cboe daily-statistics page exposed current put/call levels; those values are
not inputs and no return or PnL was computed.

## Locked candidates

All three target BTCUSDT Spot, emit only `buy`/`flat` on state changes, use a
one-day TTL and confidence 0.75, and start each scored period flat.

- buy iff the latest completed close minus the close five official observations
  earlier is strictly negative;
- otherwise flat.

No sign flip, threshold search, parameter grid, or PnL-selected combination is
allowed. A failed candidate stops under this identity.

## Evidence partitions

- 2020-01-01 through 2022-12-31 is the one-opening development reserve.
- 2023-01-01 through 2025-12-31 confirmation stays sealed until a candidate
  passes every frozen development gate.
- 2026-09-01 through 2027-01-31 remains the shared future blind.

Present-day Cboe history is official reconstruction evidence, not a claim that
each historical HTTP body existed unchanged at the decision. Missing sessions
are never filled. A close becomes eligible at the next UTC midnight.

## Provider qualification

All three CDN URLs returned HTTP 200 `text/csv` to body-free HEAD requests with
fresh last-modified timestamps. The collector may fetch each body exactly once
after this contract is committed and pushed. Schema mismatch fails closed.

## Boundaries

No credentials, SourcePolicy change, v8/v16 paper-shadow mutation, testnet
restart, confirmation PnL, future-blind access, or live path is authorized.

## Provider outcome

The one allowed VXEEM GET was opened from clean pushed commit `c0a9629`. The
response header was `DATE,OPEN,HIGH,LOW,CLOSE` rather than the frozen
`DATE,VXEEM`. Value-row audit did not run. VXEFA and VXN remain unfetched.
v17 is `blocked_provider_qualification`. An OHLC recovery needs a new identity.
