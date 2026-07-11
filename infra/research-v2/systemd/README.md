# systemd units

- **Purpose**: invoke the Research Protocol v2 one-shot Compose collector at
  three fixed UTC retry times.
- **Current phase**: seven-day provider coverage qualification.
- **Boundaries**: host scheduling only; no credentials, trading runtime, or
  automatic image updates.
- **Next implementation entrypoint**: install both unit files under
  `/etc/systemd/system/`, run `systemctl daemon-reload`, then enable the timer.

The service stops being invoked once the evidence volume contains `COMPLETE`.
Logs remain in the system journal; no webhook or mail credentials are used.
