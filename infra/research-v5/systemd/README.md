# Research Protocol v5 systemd units

- **Purpose**: invoke one append-only v5 collection batch daily, with one
  idempotent retry.
- **Current phase**: disabled templates pending the July qualification retro.
- **Boundaries**: host scheduling only; no credentials, signal generation,
  PnL review, trading runtime, or automatic checkout update.
- **Next implementation entrypoint**: install the unit files only after the
  locked commit passes cloud dry-run and one-day qualification.

The unit is separate from `nishiki-research-v2-collector.*`. It pins the current
checkout through `TRADER_GIT_SHA`; commit drift or tracked-file dirt fails
closed before any network request.
