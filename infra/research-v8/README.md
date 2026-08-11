# Research Protocol v8 forward paper shadow

This host schedule collects one credential-free, dry-run GVZ/BTC evidence
attempt after each US trading day. It writes only to the gitignored
`data/research-v8-forward/` tree. It never starts an order engine, loads
credentials, touches testnet/live, or opens the sealed future blind.

The prospectively frozen contract is
`docs/progress/phase-2-research-v8-paper-shadow.json`. Each attempt preserves an
immutable official Cboe GVZ vintage, an immutable 168-hour Binance public kline
response, incremental `SignalEvent` state, and a journal record. Multiple runs
on the same UTC date still count as at most one qualified observation day.

Install the two user units from `systemd/`, reload the user manager, and enable
the timer. The service intentionally exits non-zero on freshness, revision,
continuity, or dirty-git anomalies so they remain visible in the journal.

If the host has system cron but no user-systemd bus, install the same command
at `30 2 * * 1-5` in the `orca` user's crontab. This workspace currently uses
that fallback; `cron.service` is active and output is appended to
`data/research-v8-forward/cron.log`.
