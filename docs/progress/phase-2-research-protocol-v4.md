# Phase 2 Research Protocol v4 Provider Recovery

- **Locked**: 2026-07-17, before either direct FRED CSV body was accessed.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v4.json`
- **Provider contract**: `docs/progress/phase-2-research-v4-data-sources.json`
- **Status**: provider-recovery identities and direct CSV requests locked;
  synthetic validation passed, but both real FRED routes are blocked by response
  read timeouts from local and cloud network paths.
- **Trading effect**: none.

## Why v4 is separate

Protocol v3 remains immutable. Its hashrate route qualified, while both Stooq
macro GETs returned a JavaScript verification page instead of CSV from local
and cloud network paths. v4 does not modify those providers or identities in
place. It assigns new identities to two replacement routes and preserves the
v3 signs, observation counts, zero thresholds, evidence partitions, execution
settings, and gates.

The USD input changes economically from ICE DXY to the Federal Reserve nominal
broad trade-weighted dollar index, so it is explicitly a new factor and source:

- `rule_broad_usd_weakness_v1 / fred-dtwexbgs20obs-negative-1d-v1`;
- buy only when its 20-observation return is strictly negative.

The VIX mechanism is unchanged but the provider lineage changes to the FRED
redistribution of the Cboe daily close, so it receives a new variant identity:

- `rule_equity_vol_relief_v2 / fred-vixcls5obs-negative-1d-v1`;
- buy only when its 5-observation change is strictly negative.

## Data-access disclosure

The FRED and Cboe documentation routes were selected and stated before web
documentation search. Search summaries then exposed a few recent values. No
direct FRED CSV was opened, no return or change was calculated, and no sign,
observation count, threshold, or gate changed. v4 records this disclosure
instead of claiming zero factor-value visibility.

## Qualification contract

Both requests are credential-free FRED graph CSV GETs restricted to July 2026.
The raw envelope stores exact bytes, parsed rows, provider audit, immutable
hashes, and the retrieval timestamp. A row becomes decision-eligible no earlier
than `retrieved_at`; v4 does not infer a historical publication time from its
observation date.

Missing FRED `.` values are retained and counted but never forward-filled. The
qualification collector must reject duplicate/non-increasing dates, unexpected
columns, non-finite or non-positive observations, future dates, out-of-July
rows, tampering, and overwrite attempts.

A present-day FRED CSV is not a valid 2020-2022 point-in-time reserve. Historical
replication stays closed until a separately qualified vintage route exists.
July remains schema/lineage/freshness-only; August-December 2026 remains the
final future blind.

## Explicit boundaries

- Do not generate factors, returns, signals, or PnL during provider qualification.
- Do not implement the v4 SignalEvent generator until both direct CSV routes pass.
- Do not modify v3 identities or retry Stooq through an unregistered challenge.
- Do not change SourcePolicy, run promotion review, resume testnet, or touch live.

## 2026-07-17 provider qualification result

Pre-registration commit `62d926f` was pushed before either direct CSV GET ran.
The exact commit was deployed separately on the cloud server from archive
SHA-256 `56eb5198b4885a5a389c7e21c78325b09ce6dfd25aac349473a5a7b0cf6e4050`.
Protocol validation and both network-disabled dry-runs passed in the existing
Python 3.12 read-only research container.

Both real FRED GETs then failed during HTTPS response reading after the fixed
30-second timeout. The broad USD timeout was reproduced on the cloud path; the
VIX timeout was reproduced on both cloud and local paths. Earlier local combined
collection also produced no file. Neither
`/var/lib/nishiki-trader/research-v4/raw` nor `data/research-v4/raw` contains a
snapshot.

The result is `blocked_provider_response_timeout` for both v4 candidates. No
schema, factor, return, signal, or PnL was accepted. Do not implement the v4
SignalEvent generator or automatically create another provider-recovery
protocol. Full evidence is in
`docs/retros/2026-07-17-research-v4-provider-qualification.md`.
