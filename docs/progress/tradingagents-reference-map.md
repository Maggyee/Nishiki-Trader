# TradingAgents Reference Map

- **Status**: Active reference note
- **Created**: 2026-06-11
- **Upstream checkout**: `TradingAgents/` at `04f434e86db88e7707bf16db8ed7183f9764fe26`
- **Purpose**: Turn the TradingAgents source checkout into a practical reference for future agent configuration without weakening this project's execution boundaries.

This note is a map, not an adoption plan. TradingAgents remains a read-only
upstream reference; this project does not install it, import it at runtime, or
copy its trader / portfolio-manager execution semantics.

The first project-owned machine-readable layer is
`apps.agents.role_profiles`. It exposes safe AgentAdvice-only role profiles and
the CLI command `python -m apps.agents.cli profiles`; it still does not run
agents or call an LLM.

## Useful Patterns To Borrow

| TradingAgents pattern | Upstream files inspected | Project-safe adaptation |
|---|---|---|
| Role decomposition into analysts, researchers, risk reviewers, and managers | `tradingagents/agents/`, `tradingagents/graph/setup.py` | Use the role vocabulary to define future `AgentAdvice` producers: evidence reviewer, data anomaly analyst, macro/news summarizer, strategy brainstormer. |
| Explicit debate loop limits | `tradingagents/graph/conditional_logic.py`, `tradingagents/default_config.py` | Keep bounded review rounds such as `max_debate_rounds=1` when a future orchestrator asks multiple agents to critique an idea. |
| Structured output for manager/trader-style nodes | `tradingagents/agents/schemas.py` | Recast structured outputs as `AgentAdvice` payloads with non-execution fields only: thesis, evidence, risks, confidence, suggested human review action. |
| Env-var-driven config overrides | `tradingagents/default_config.py` | If an agent orchestrator is added later, prefer explicit `TRADER_AGENT_*` env overrides for provider/model/depth settings, not hidden global state. |
| Checkpoint/resume by deterministic run identity | `tradingagents/graph/checkpointer.py` | Future long-running analysis jobs may checkpoint by `(agent_name, evidence_set, as_of_date)` in a local ignored SQLite file; checkpoints must not authorize actions. |
| CLI progress display and report section aggregation | `cli/main.py` | Useful for operator ergonomics if a future analysis CLI streams agent progress; final artifact still writes `AgentAdvice`. |

## Patterns Not To Borrow

| Upstream behavior | Why it is unsafe here |
|---|---|
| Trader agent emits transaction proposals with entry / stop / sizing fields | `AgentAdvice` rejects structured execution fields; this project keeps sizing and execution inside NautilusTrader policies and risk checks. |
| Portfolio Manager approves/rejects a transaction proposal | Human review of `AgentAdvice` is audit metadata only; it cannot authorize trading behavior. |
| Backtrader dependency for simulation | NautilusTrader is the only execution and backtest engine for project-owned trading paths. |
| Direct market-data vendor calls inside agent tools | Future agents should read approved local artifacts first. Any external data fetcher needs a separate boundary review and must not touch exchange APIs. |
| Multi-agent graph as a default runtime | ADR-001 explicitly defers multi-agent collaboration until one agent is stable; start with deterministic or single-agent flows. |

## Safe Agent Role Vocabulary

These names are safe candidates for future `agent_name` values because they
describe research or review work rather than execution authority:

| Candidate agent | Inputs | Output |
|---|---|---|
| `evidence_review_agent` | `docs/project-status.md`, canary evidence, bundle reports | `advice_type="project_review"` or `advice_type="evidence_review"` |
| `data_anomaly_agent` | dashboard snapshots, passive observability summaries, bundle sidecar reports | `advice_type="anomaly_observation"` |
| `macro_context_agent` | curated news / macro summaries once an approved source exists | `advice_type="market_context"` |
| `strategy_brainstorm_agent` | historical reports, rejected signal summaries, user prompts | `advice_type="strategy_note"` |
| `parameter_review_agent` | paper/testnet evidence and existing SourcePolicy docs | `advice_type="parameter_candidate"` |

These are now encoded in `apps.agents.role_profiles.DEFAULT_AGENT_ROLE_PROFILES`.
Use `uv run python -m apps.agents.cli profiles` to inspect the current profile
set.

Unsafe names such as `trader_agent`, `portfolio_manager_agent`, or
`execution_agent` should be avoided unless a future ADR deliberately redefines
them as non-executing aliases.

## Minimum Future Implementation Path

1. Extend `apps.agents.review_agent` or add a sibling deterministic analyzer
   that reads only local docs/reports and writes `AgentAdvice`.
2. Reuse `apps.agents.role_profiles.AgentRoleProfile` as the role/config seed.
3. Add one small config surface for model/provider/depth only after a real LLM
   call is introduced. Keep provider credentials in ignored env files.
4. Keep all external tool access behind MCP-facing safe wrappers that cannot
   import `SignalStore` write paths, `SourcePolicy` mutation paths, or exchange
   clients.
5. Add tests that prove any TradingAgents-inspired payload cannot parse as
   `SignalEvent` and is rejected if it contains execution fields.
6. Only after the single-agent loop is useful, consider a bounded two-role
   debate such as `bull_case` vs `bear_case`, with the merged output still
   stored as one `AgentAdvice` row.

## Boundary Checklist

Before any future TradingAgents-inspired implementation is merged, verify:

- no import from `TradingAgents/` exists in project-owned runtime code;
- no new dependency such as LangGraph or Backtrader is added without an ADR;
- no agent writes `SignalEvent`, `SourcePolicy`, order, fill, or position rows;
- no agent calls Binance, Nautilus execution clients, or emergency-flatten code;
- payload keys remain compatible with `apps.agents.advice.AgentAdvice`;
- dashboard/frontend surfaces remain read-only consumers of `AgentAdvice`.
