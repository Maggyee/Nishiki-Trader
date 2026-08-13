# Progress Archives

- **Purpose**: Archive detailed implementation history that is too long for `docs/project-status.md`.
- **Current phase**: Phase 5 entry.
- **Boundaries**: This directory is for historical progress snapshots, handoff notes, and phase summaries. It is not the source of truth for current next steps; use `docs/project-status.md` for that.
- **Next implementation entrypoint**: When `docs/project-status.md` starts accumulating changelog detail, summarize the durable facts there and move the detailed history into a dated or phase-scoped file in this directory.

Rules:

- Keep `docs/project-status.md` short enough to read at task start.
- Put detailed completed-work lists, long verification transcripts, and implementation narratives here.
- Put permanent architecture decisions in `docs/decisions/`, not here.
- Link archive files from `docs/project-status.md` only when they remain useful context.

Current Phase 3 progress files:

- `phase-2-research-protocol-v2.md` and its JSON contract lock the three
  independent-mechanism candidates, point-in-time data rules, evidence
  partitions, costs, and anti-overfit gates before real factor access.
- `phase-2-research-v2-data-sources.json` locks credential-free Deribit,
  Binance COIN-M, and Coin Metrics qualification endpoints plus the immutable
  raw-snapshot envelope before any response body is fetched.
- `phase-2-research-protocol-v3.md` and its JSON contract lock three new
  macro/native mechanisms (hashrate recovery, DXY weakness, VIX relief) without
  reopening rejected v1 families or blocked v2 data routes.
- `phase-2-research-v3-data-sources.json` locks credential-free Blockchain.com
  hashrate and Stooq DXY/VIX qualification endpoints before response-body
  access.
- `phase-2-research-protocol-v17.md` and its JSON/provider contracts lock
  VXEEM, VXEFA, and VXN five-observation relief; provider qualification then
  failed closed on the VXEEM OHLC header.
- `phase-2-research-protocol-v18.md` recovers those rules under new OHLC
  identities. Nasdaq vol relief passed development and independent 2023-2025
  confirmation, then entered identity-specific `paper_shadow` dry-run hold;
  prospective collection has not started.

- `phase-3-testnet-canary-evidence.md` records the testnet session ledger and
  bundle evidence summary.
- `phase-3-testnet-continuity-plan.md` defines the 14-day continuity tracking
  plan and the `report_testnet_bundle --continuity` review command.
- `tradingagents-reference-map.md` maps the ignored TradingAgents upstream
  checkout to project-safe AgentAdvice-only role/configuration ideas.
- `phase-5-dashboard-history.md` archives completed read-only dashboard,
  AgentAdvice input, passive Phase 6 gate, and dashboard hardening history that
  is too detailed for `docs/project-status.md`.
