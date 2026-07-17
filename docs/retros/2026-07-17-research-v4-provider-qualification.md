# 2026-07-17 Research Protocol v4 Provider Qualification

- **Status**: Blocked; both FRED direct CSV routes timed out before a response
  body was accepted.
- **Pre-access commit**: `62d926f` pushed to `origin/main`.
- **Scope**: July schema, immutable lineage, missing-value behavior, and
  snapshot-time availability only.
- **Snapshots created**: zero.
- **PnL accessed**: no.
- **Trading effect**: none.

## Locked recovery routes

v4 was created separately from immutable v3 after Stooq returned browser
verification pages. It locked two credential-free, July-only FRED graph CSV
requests:

- `DTWEXBGS` for the Federal Reserve nominal broad U.S. dollar index under new
  identity `rule_broad_usd_weakness_v1 /
  fred-dtwexbgs20obs-negative-1d-v1`;
- `VIXCLS` for the Cboe VIX daily close redistributed by FRED under new identity
  `rule_equity_vol_relief_v2 / fred-vixcls5obs-negative-1d-v1`.

Signs, observation counts, zero thresholds, costs, gates, and evidence
partitions were inherited from v3. Documentation search exposed limited current
rows only after the routes were chosen; the machine contract discloses this.
No return, change, threshold comparison, or PnL was calculated.

## Pre-access verification

The protocol and provider fingerprints, 19 synthetic tests, Ruff, and both
network-disabled dry-runs passed before the direct CSV GETs. The deployed cloud
archive SHA-256 was:

```text
56eb5198b4885a5a389c7e21c78325b09ce6dfd25aac349473a5a7b0cf6e4050
```

Cloud execution used a read-only root filesystem, read-only v4 code mount,
dropped capabilities, no credentials, and only the empty v4 raw directory as a
writable mount. The completed v2 deployment, image, timer, and evidence were not
modified or restarted.

## Real-request result

The cloud broad USD request failed while waiting for the HTTPS response status
line after 30 seconds. A retained retry log records `TimeoutError: The read
operation timed out`. The cloud VIX request failed at the same point with the
same timeout. Both exited 1 and wrote no files.

The local path also produced no broad USD or VIX snapshot. A retained local VIX
run independently records the same 30-second HTTPS response-read timeout. No
HTML, CSV rows, parsed values, or partial envelope were accepted as evidence.

```text
broad_usd=blocked_provider_response_timeout
vix=blocked_provider_response_timeout
cloud_snapshot_count=0
local_snapshot_count=0
```

## Boundary audit and decision

No credentials, factor CSV, derived factor, return, SignalEvent, SignalStore
row, Nautilus run, PnL, SourcePolicy change, testnet resume, or live action
occurred. The 2020-2022 reserve and 2026-08..12 future blind remain unopened.

Keep v3 and v4 immutable. Do not add a v4 SignalEvent generator, route through a
proxy, increase timeouts to fish for a response, or automatically create a v5
provider substitution. The only currently qualified v3 macro/native route is
hashrate. Any future macro provider attempt needs new independent evidence and
an explicit review of whether continued provider search is worth the
multiple-testing and maintenance cost.
