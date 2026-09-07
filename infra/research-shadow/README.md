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

V46/v48 forward-only adapters use checksum-verified completed monthly archives
plus closed daily archives for the current month, caching verified archives.
The frozen historical qualification modules and strategy parameters are unchanged.
Only yesterday's unpublished daily archive can be absent (maximum age 2 days);
other coverage, checksum, or network failures fail closed. No future-blind PnL
is computed. Seven days remain a pipeline check, never alpha evidence.
