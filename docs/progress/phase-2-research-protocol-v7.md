# Phase 2 Research Protocol v7

- **Frozen**: 2026-08-11, before reading any Cboe historical CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v7.json`
- **Provider contract**: `docs/progress/phase-2-research-v7-data-sources.json`
- **Status**: replication complete; all three candidates rejected; future blind sealed.
- **Trading effect**: none.

## Why this protocol is allowed

The 16-family stop rule remains binding. Protocol v7 does not retune an OHLCV,
funding, flow, or rotation model. It introduces official Cboe implied-volatility
histories as independently justified evidence. The earlier v3/v4 VIX routes
were blocked at Stooq/FRED; this protocol uses a new official provider contract
and new source/model identities rather than changing those frozen identities.

## Locked candidate batch

All three candidates target BTCUSDT Spot, use one-hour execution bars, start
every fold flat, and emit only long/flat `SignalEvent v1` state changes:

1. VIX equity-volatility relief;
2. OVX energy-volatility relief;
3. GVZ gold-volatility relief.

For each index, `buy` is allowed only when the latest completed close minus the
close five official observations earlier is strictly negative. Zero or a
positive change is `flat`. The threshold, lookback, candidate count, costs,
universe, and gates are frozen. There is no grid search, sign flip, PnL-selected
ensemble, or symbol substitution.

## Evidence partitions and gates

- 2020-01-01 through 2022-12-31 is the one-opening replication reserve.
- 2023-01-01 through 2026-08-10 is diagnostic-only and must not select a rule.
- 2026-09-01 through 2027-01-31 is the untouched five-month future blind.

Replication requires positive base and stress PnL, at least two positive years,
at least half of months positive, at least 30 closed positions, positive base
PnL after removing the best position, Spot long/flat lineage, and two exact
replays. A passing replication candidate remains research-only until it later
passes the sealed future blind.

## Provider and point-in-time contract

The three URLs are the daily historical downloads linked by Cboe's official
VIX historical-data page. Each snapshot must retain exact response bytes and
hashes. A session close becomes eligible only at the next UTC midnight; missing
sessions are not filled. The signal generator must preserve the provider
vintage and snapshot fingerprint in every event.

## Boundaries

This protocol cannot load credentials, modify `SourcePolicy`, restart testnet,
or touch live trading. The pre-access baseline must be committed and pushed
before any CSV body is downloaded.

## Replication result

The one allowed 2020-2022 opening is complete. VIX is cost-positive but fails
leave-best concentration; OVX is cost-negative; GVZ passes the numeric gates
but is rejected by the pre-registered execution-catalog blocker because the
official BTCUSDT 1h archive has 30 missing intervals. All duplicate replays
match. No candidate advances and the 2026-09..2027-01 blind remains sealed.
See `docs/retros/2026-08-11-research-v7-replication-review.md`.
