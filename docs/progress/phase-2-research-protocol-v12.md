# Phase 2 Research Protocol v12

- **Frozen**: 2026-08-12, before opening any 2026 Coin Metrics stablecoin
  response body under this identity.
- **Status**: Day 0 pipeline qualification passed; genuine forward evidence
  remains 0/180 observations and 0/2 state changes.
- **Stage**: `forward_data_candidate`; not `paper_shadow`.
- **Trading effect**: none.

## Purpose

Protocol v11 found positive cost-adjusted historical PnL for aggregate
USDT+USDC supply expansion, but only seven closed positions. V12 does not
reinterpret that as a pass and does not change the rule. It creates genuinely
forward, immutable data evidence for the exact 30-observation positive-change
mechanism.

## Information timing

Each daily Coin Metrics `SplyCur` observation for UTC day D is eligible only at
D+2 00:00 UTC. The collector requests a fixed daily history beginning
2026-06-01 so revisions can be detected. Observations before 2026-08-12 seed
the 30-day state but never count as forward evidence. The first countable
observation is therefore 2026-08-12 and its earliest decision time is
2026-08-14.

Every attempt also preserves a public Binance BTCUSDT hourly overlap. Missing
stablecoin days, missing assets, revised historical values, BTC gaps, BTC
revisions, dirty code, or an unpushed collector commit fail closed. No row is
forward-filled or synthesized.

## Review threshold

A review becomes eligible only after both 180 distinct qualified forward
observation days and two genuinely forward state-change events. That review
may decide only whether the long collection should continue. It does not open
v11 confirmation, paper trading, SourcePolicy, testnet, live trading, or the
shared future blind.

## Day 0 qualification

The first manual attempt ran from clean pushed commit `70c53a2`. It retained a
complete 142-row USDT/USDC daily grid through 2026-08-10 and 167 contiguous
closed BTCUSDT hourly bars, with zero detected revisions and zero blockers.
Because the target factor date predates the 2026-08-12 forward boundary, it is
bootstrap evidence only and contributes zero forward observations or state
changes. Detailed status is in
`docs/progress/phase-2-research-v12-forward-status.json`.
