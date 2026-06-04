# ADR-009: AgentAdvice Audit Store And LLM Isolation

- **Status**: Accepted
- **Date**: 2026-06-04
- **Owner**: nishiki
- **Scope**: Phase 4 entry foundation for LLM/agent research outputs.
- **Depends on**: ADR-001, ADR-002, ADR-005, ADR-007, ADR-008.

## 1. Context

Phase 3 testnet canary collection is paused by operator decision, and the
project is moving development toward Phase 4 agent research. Several earlier
ADRs reserved ADR-009 for the LLM / AgentAdvice boundary, but no concrete
artifact existed yet.

The first Phase 4 implementation must be deliberately narrow: agents need a
place to write journals, retro notes, analysis, and candidate parameter ideas,
but they still must not write `SignalEvent v1`, change `SourcePolicy`, call
exchange APIs, or enter the live order path.

## 2. Decision

Introduce `AgentAdvice v1` as a separate audit record:

```json
{
  "schema_version": "agent.advice.v1",
  "advice_id": "review_agent:journal:1778760000000000000:abc123",
  "agent_name": "review_agent",
  "created_at_ns": 1778760000000000000,
  "advice_type": "journal",
  "summary": "testnet evidence is operational, not alpha",
  "confidence": 0.8,
  "payload": {"content": "human-readable research note"},
  "tags": ["testnet", "retro"],
  "source_refs": ["docs/progress/phase-3-testnet-canary-evidence.md"]
}
```

`AgentAdvice` is stored in SQLite at `data/agents/advice.db` by default, table
`agent_advice`. SQLite remains the default Phase 4 entry store until a concrete
Phase 4 workload proves that Postgres-backed agent memory is required.

## 3. Boundary

`AgentAdvice` is not a signal, not an order, and not a policy mutation.

Allowed:

- journal and retro notes;
- offline analysis summaries;
- anomaly observations;
- candidate parameter suggestions for human review;
- references to bundle paths, docs, or reports.

Forbidden:

- writing to `signals` / `signal_events`;
- changing source authorization or `SourcePolicy`;
- calling live/testnet exchange APIs;
- embedding structured direct execution fields such as `order_type`,
  `quantity`, `leverage`, `stop_loss`, `take_profit`, `reduce_only`, or
  `time_in_force`.

Human review decisions (`accepted`, `ignored`, `rejected`) are audit metadata
only. A reviewed `AgentAdvice` row still does not authorize trading behavior.

## 4. Phase 4 Entry Implementation

The initial implementation is:

- `apps.agents.advice.AgentAdvice` Pydantic schema.
- `apps.agents.store.AgentAdviceStore` SQLite store with WAL enabled.
- `apps.agents.cli` for JSON/JSONL writes, journal writes, replay, and human
  review annotation.
- Focused tests under `tests/agents/`.

No Claude SDK client, MCP server, external LLM calls, message bus, or long-lived
agent process is introduced by this ADR.

## 5. Verification Standard

The implementation must prove:

1. `AgentAdvice` rows validate and round-trip through SQLite.
2. `AgentAdvice` cannot be parsed as `SignalEvent`.
3. Agent payloads with structured execution fields are rejected.
4. Duplicate `advice_id` rows are rejected.
5. Replay filters by agent, advice type, status, and time window.
6. CLI writes and reads JSONL without touching `signals`.

## 6. Future Work

- Add read-only MCP wrappers around the store.
- Add a single mock-LLM review agent that writes only `AgentAdvice`.
- Define any `llm_*` SignalEvent experiments in a separate ADR before they can
  move beyond paper shadow. Until then, LLM outputs stay outside the signal
  bridge.

**Decided.** Phase 4 starts with an audit store, not an autonomous trading
agent. `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` remains the
only trading-intent bridge.
