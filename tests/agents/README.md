# tests/agents

- **Purpose**: Phase 4 AgentAdvice schema, SQLite audit-store, CLI, and
  deterministic review-agent tests.
- **Current phase**: Phase 4 entry.
- **Boundaries**: Tests verify that agent output stays in `agent_advice`, does
  not become `SignalEvent`, and rejects structured execution directives.
- **Next entrypoint**: Add orchestrator or real LLM-client tests here only if
  they keep outputs in AgentAdvice and outside `SignalEvent`.
