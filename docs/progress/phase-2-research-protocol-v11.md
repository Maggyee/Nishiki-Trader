# Phase 2 Research Protocol v11

- **Frozen**: 2026-08-11, after v10 schema qualification but before factor
  values, signals, or PnL were opened.
- **Status**: pre-registered; development unopened.
- **Trading effect**: none.

V10 proved that all three Community API routes have complete 2019-11 through
2022 coverage but return no status-time metadata, so v10 closed without
testing. V11 keeps all three economic rules and lookbacks unchanged, reuses
the exact immutable v10 response bytes without refreshing them, and changes
only the explicitly declared information-time model.

`HashRate`, `SplyCur`, and `FeeTotNtv` are daily ledger-derived metrics. V11
treats the observation for UTC day D as a reconstruction from the canonical
finalized public ledger and permits it only at D+2 00:00 UTC. No missing day is
forward-filled and no provider vintage claim is made. Because present-day
transport can still contain later methodology corrections, a historical pass
is replication evidence only; promotion would require genuinely forward,
immutable daily snapshots.

The development, confirmation, cost, activity, breadth, concentration, and
duplicate-replay gates remain the same as v10. Confirmation and the shared
future blind remain sealed until the preceding stage passes.
