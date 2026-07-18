# Research Protocol v5 systemd units

- **Purpose**: invoke one append-only v5 collection batch daily, with one
  idempotent retry.
- **Current phase**: deployed and enabled after the historical fast-track
  report commit; first scheduled collection is 2026-07-18 04:15 UTC.
- **Boundaries**: host scheduling only; no credentials, signal generation,
  PnL review, trading runtime, or automatic checkout update.
- **Next implementation entrypoint**: monitor the first scheduled batch and
  retain both successes and explicit flat failures without changing the unit.

The unit is separate from `nishiki-research-v2-collector.*`. It invokes the
dedicated `nishiki-research-v5:<TRADER_GIT_SHA>` one-shot container; the image's
read-only build marker, environment, and CLI commit must agree before any
network request. A host-checkout run additionally rejects tracked-file dirt.
