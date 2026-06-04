# tests/mcp_server

- **Purpose**: Phase 4 MCP-facing tool boundary tests.
- **Current phase**: Phase 4 entry.
- **Boundaries**: Tests cover safe AgentAdvice wrappers only. They must not
  expose order placement, SignalEvent writes, SourcePolicy mutation, or
  exchange API access.
- **Next entrypoint**: Add real MCP protocol handler tests here if the project
  later introduces an MCP SDK dependency.
