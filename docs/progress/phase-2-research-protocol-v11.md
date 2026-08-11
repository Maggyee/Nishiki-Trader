# Phase 2 Research Protocol v11

- **Frozen**: 2026-08-11, after v10 schema qualification but before factor
  values, signals, or PnL were opened.
- **Status**: development complete; hashrate and fee demand rejected;
  stablecoin expansion is insufficient evidence; confirmation sealed.
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

## Development result

All three candidates reproduced exactly and passed execution evidence checks.
Hashrate recovery is cost-positive but fails monthly breadth and leave-best
concentration. BTC fee demand is negative after costs and also fails breadth
and concentration. Stablecoin expansion is strongly cost-positive but has only
seven closed positions and is dominated by its best position, so it is marked
insufficient evidence rather than rejected as a negative return result. No
candidate may open confirmation. See
`docs/retros/2026-08-11-research-v11-native-fundamentals-development.md`.
