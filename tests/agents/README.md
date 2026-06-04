# tests/agents

- **Purpose**: Phase 4 AgentAdvice schema, SQLite audit-store, and CLI tests.
- **Current phase**: Phase 4 entry.
- **Boundaries**: Tests verify that agent output stays in `agent_advice`, does
  not become `SignalEvent`, and rejects structured execution directives.
- **Next entrypoint**: Add mock-LLM/orchestrator tests here when
  `apps.agents` grows beyond the audit store.
