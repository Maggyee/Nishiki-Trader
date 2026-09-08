# Shared forward collector runtime

Phase 5 reliability repair, authorized 2026-09-07. Existing ten schedules keep
their cadence and research identities; no new live service or order path.

Entrypoint after a clean commit is pushed:

```bash
.venv/bin/python -m apps.ops.install_shadow_collectors --install
```

This pins the existing crontab entries to an immutable local checkout under
`data/collector-deployments/<commit>`, keeping original data roots and logs.
It saves the prior crontab, refuses duplicates/unknown checkout ownership,
and verifies the installed text. Reinstall after a reviewed runtime update.
Restore the saved crontab only after checking that no other jobs changed.

All runtime statuses now live under the respective `data/` roots. Tracked
`docs/progress/*paper-shadow-status.json` files are historical snapshots.
Collectors must never write to them. A passive monitor reads runtime statuses.

The strict collectors reconstruct the capture cursor from retained BTC response
bodies whose hashes match immutable attempt journals. They do not fetch missing
historical bars or reclassify failed days. Historical anomaly blockers remain
visible and continue to require human review even when new collection succeeds.

V40/v42/v46/v48 use `research.shadow.runtime.v2`: qualified distinct dates,
new observations, forward signal IDs, freshness, revision detection, immutable
factor files, a lock and atomic status writes. The old state.json and run counts
remain preserved but are not imported as qualified evidence. Prospective
accounting begins with runtime-state.json; it does not reset research identity.

V22/v34/v36 additionally use a signal-pipeline v2 epoch (2026-09-08 repair).
Generators receive an explicit observation-date upper bound and reject reversed
ranges. `state/signal-pipeline-v2.json` starts prospective accounting only after
a successful corrected run. Earlier attempts remain retained history, not
qualified signal-generation days; recovered historical signals are not new
forward signals. Status exposes the epoch, generated signal count, and legacy
attempt count. Zero signals can be legitimate in a flat factor window, so tests
must exercise known transitions as well as successful collection.
The monitor derives all ten source/model pairs from frozen shadow contracts;
v36 is VPN expansion / positive diff5, not relief / negative diff5.

V46/v48 forward-only adapters use checksum-verified completed monthly archives
plus closed daily archives for the current month, caching verified archives.
If an official monthly archive omits a day, that exact date must be recovered
from a checksum-verified official daily archive. Missing values are never filled
with prices or zero. Original monthly bytes and receipts remain unchanged.
The Cboe gap check covers the unchanged 90-day factor window, not unrelated old
market closures in the full provider CSV.
The frozen historical qualification modules and strategy parameters are unchanged.
Only yesterday's unpublished daily archive can be absent (maximum age 2 days);
other coverage, checksum, or network failures fail closed. No future-blind PnL
is computed. Seven days remain a pipeline check, never alpha evidence.
