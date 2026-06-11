# app

- **Purpose**: Phase 5 entry Next.js dashboard route files.
- **Current phase**: Phase 5 entry.
- **Boundaries**: Server components may read `dashboard.snapshot.v1` from local
  files. They must not write `SignalEvent`, mutate `SourcePolicy`, call exchange
  APIs, or expose order-placement controls.
- **Next entrypoint**: Add read-only dashboard routes or panels that consume the
  same snapshot contract, such as signal-source distribution or rejection
  summaries from approved reports.
