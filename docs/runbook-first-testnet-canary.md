# Runbook — First real testnet canary session

- **Status**: Active. Tracks ADR-008 §6.6 follow-up after the §8
  promotion-review patch landed and the first
  `paper_simulated → testnet_canary` promote retro was signed.
- **Audience**: nishiki, operating solo on the control machine.
- **Scope**: The **first** real session where a strategy is actually
  registered and let to drive Binance Spot testnet orders. Every
  later canary session may reuse this runbook but must re-run §1 from
  scratch.

This is a hands-on operating procedure, not a code change. Read every
section before opening any terminal. The procedure assumes:

- `apps/strategies_nautilus/runners/testnet_runner.py --long-run` with
  `--enable-strategy-execution` is wired (Phase 3f follow-up commit).
- `BaselineNautilusStrategy` accepts a `SignalStorePollingSource` (Phase
  3f follow-up commit).
- The promote retro at
  `docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md` is
  already signed.

If any of those is not true, **stop** and complete the prerequisite first.

---

## 1. Preflight checklist

Run each of these in order. Do not proceed if any item fails. The whole
checklist should take ≤ 5 minutes.

### 1.1 Repo state

```bash
git fetch origin
git pull --ff-only
git status --short --branch   # must be clean and == origin/main
git log --oneline -3
```

The runner refuses to start if `git status --porcelain` is non-empty.

### 1.2 Promote retro on disk

```bash
ls -la docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md
grep "decision_allowed: \*\*yes\*\*" \
  docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md
grep "position_pct_multiplier: 0.2 -> 0.1" \
  docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md
```

### 1.3 Test suite + lint baseline

The session is going to write real testnet orders. Confirm nothing in
the local tree is broken before you start a 6 h run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra
```

Both must pass.

### 1.4 Credentials present (but never inspected)

```bash
test -f ~/.config/trader/binance_testnet.env || \
  echo "MISSING: ~/.config/trader/binance_testnet.env"
```

The file must contain only `BINANCE_TESTNET_API_KEY=…` and
`BINANCE_TESTNET_API_SECRET=…` lines, the secret being an Ed25519
PEM-PKCS#8 private key. **Do not** cat the file — load it via
`set -a; . ~/.config/trader/binance_testnet.env; set +a` later in §4.

### 1.5 SignalStore can produce a current `freqai_linear_v1` row

Verify the bridge DB exists and the source/model_version filter returns
something. The launcher's `SignalStorePollingSource` only fires on new
rows after start, so signals must keep arriving while the session runs.
Until a real online FreqAI producer exists, use the wall-clock replay helper
to copy reviewed historical rows into future timestamps. The helper preserves
`source=freqai_linear_v1` / `model_version=linear-mom-train20240105` for
SourcePolicy authorization and records the original row in
`metadata.wall_clock_replay`.

```bash
uv run python -c "
from apps.bridge.store import SignalStore
import time
store = SignalStore('data/bridge/signals.db')
recent = store.replay(
    source='freqai_linear_v1',
    model_version='linear-mom-train20240105',
    since_ns=time.time_ns() - 24 * 3_600 * 1_000_000_000,
)
print('rows_last_24h=', len(recent))
print('latest_ts_event_ns=', recent[-1].ts_event if recent else None)
"
```

Dry-run the restamp first:

```bash
uv run python -m apps.strategies_freqtrade.research.wall_clock_signal_replay \
  --input-store-path data/bridge/signals.db \
  --output-store-path data/bridge/signals.db \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --start-delay-seconds 180 \
  --interval-seconds 60 \
  --max-signals 3 \
  --min-confidence 0.55 \
  --side buy \
  --ttl-seconds 900 \
  --dry-run
```

Then run the same command without `--dry-run` shortly before starting the
canary. The 180 s delay gives the runner time to start with its initial
SignalStore cursor before the first restamped event becomes due.

### 1.6 Catalog still serves BTCUSDT 1m

```bash
ls data/catalog/data/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/ | head -3
```

Strategy depends on the bar type
`BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL` being subscribable. The
live-WS path serves this directly via the Binance adapter; the local
catalog only matters for offline diff.

---

## 2. Choose session parameters

Lock these down **before** starting the launcher:

| parameter | first-canary value | note |
|---|---|---|
| `source` | `freqai_linear_v1` | matches the signed promote retro |
| `model_version` | `linear-mom-train20240105` | identical fingerprint v3/v6/v7/v8/v9/v10 |
| `position_pct_multiplier` | `0.1` | half of paper_simulated 0.2 |
| `trade_size` | `0.001` BTC (≈ $30 at $30k spot) | matches paper bundles |
| `max_run_seconds` | `21600` (6 h) | matches Phase 3f stability soak |
| `starting_balance` | testnet faucet (`10000` USDT default) | observed in Phase 3b probe |
| `daily_loss_limit_pct` | `0.05` | ADR-001 kill-switch threshold |
| `instrument_id` | `BTCUSDT.BINANCE` | Phase 3 scope is single instrument |
| `bar_type` | `BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL` | unchanged from Phase 3a |

Pick a `run_id` that is unique. The runner auto-generates one; record
it as soon as it shows up in the runner stdout.

---

## 3. Prepare the launcher script

The runner CLI itself **cannot** wire a strategy (it has no flag for
`BarType` / `InstrumentId` / SignalStore path). The wiring belongs to a
small Python launcher that the operator owns. Copy the block below into
`infra/launchers/first-testnet-canary.py` (create the directory if it
does not exist; it is gitignored).

```python
"""Operator-owned launcher for the ADR-008 §6.6 first testnet canary.

This script is intentionally not committed: it carries the operator's
chosen run-time numbers and is the explicit human-readable trigger that
turns signal flow into real testnet orders.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from apps.strategies_nautilus.baseline_nautilus_strategy import LineageRecord
from apps.strategies_nautilus.runners import testnet_runner
from apps.strategies_nautilus.runners.first_testnet_canary import (
    FirstCanaryStrategySpec,
    build_register_strategies,
)


def _build_argv() -> list[str]:
    return [
        "--mode", "testnet",
        "--kind", "testnet",
        "--allow-real-credentials",
        "--source", "freqai_linear_v1",
        "--model-version", "linear-mom-train20240105",
        "--policy-position-pct-multiplier", "0.1",
        "--retros-dir", "docs/retros",
        "--repo-root", str(Path.cwd()),
        "--operator", "nishiki",
        "--instrument-id", "BTCUSDT.BINANCE",
        "--long-run",
        "--starting-balance", "10000",
        "--max-run-seconds", "21600",
        "--telemetry-poll-seconds", "1.0",
        "--heartbeat-interval-seconds", "30.0",
        "--daily-loss-limit-pct", "0.05",
        "--output-root", "data/testnet",
        "--enable-strategy-execution",
    ]


def main() -> int:
    spec = FirstCanaryStrategySpec(
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        signal_store_path=Path("data/bridge/signals.db"),
        instrument_id_str="BTCUSDT.BINANCE",
        bar_type_str="BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
        trade_size=Decimal("0.001"),
        base_currency_code="USDT",
        venue="BINANCE",
        position_pct_multiplier=0.1,
    )
    lineage: list[LineageRecord] = []
    register = build_register_strategies(spec, lineage=lineage)
    return testnet_runner.main(_build_argv(), register_strategies=register)


if __name__ == "__main__":
    raise SystemExit(main())
```

Read the script before saving. Two responsibilities live here that the
runner CLI cannot enforce:

- `FirstCanaryStrategySpec.position_pct_multiplier` matches the
  `--policy-position-pct-multiplier` value passed to the runner. If you
  edit one, edit both.
- `lineage` is a plain `list[LineageRecord]` that the strategy mutates
  in place. After the run completes the launcher does **not** write a
  sidecar — the lineage rows are reachable only inside the still-running
  Python process. Until a sidecar writer lands, treat lineage as a live
  debugging probe, not as an artifact. The runner manifest is the
  durable audit.

---

## 4. Start watchdog (background terminal)

In a dedicated terminal, start the watchdog **before** the runner.

```bash
mkdir -p /tmp/phase3f-canary
cat > /tmp/phase3f-canary/watchdog_loop.sh <<'EOF'
#!/usr/bin/env bash
set -u
while true; do
  UV_CACHE_DIR=/tmp/uv-cache uv run python -m infra.watchdog.watchdog \
    --bundle-root data/testnet \
    --heartbeat-timeout-seconds 90 \
    --kind testnet \
    --operator nishiki >> /tmp/phase3f-canary/watchdog.loop.log 2>&1
  sleep 30
done
EOF
chmod +x /tmp/phase3f-canary/watchdog_loop.sh
nohup /tmp/phase3f-canary/watchdog_loop.sh >/dev/null 2>&1 &
echo $! > /tmp/phase3f-canary/watchdog.pid
```

Confirm it is alive:

```bash
ps -p "$(cat /tmp/phase3f-canary/watchdog.pid)" -o pid,etime,stat
```

---

## 5. Start the canary (foreground terminal)

```bash
set -a
. ~/.config/trader/binance_testnet.env
set +a
test "${#BINANCE_TESTNET_API_KEY}" -ge 32 || { echo "key too short"; exit 1; }
test "${#BINANCE_TESTNET_API_SECRET}" -ge 32 || { echo "secret too short"; exit 1; }

mkdir -p /tmp/phase3f-canary
UV_CACHE_DIR=/tmp/uv-cache nohup uv run python \
  infra/launchers/first-testnet-canary.py \
  > /tmp/phase3f-canary/runner.stdout.log \
  2> /tmp/phase3f-canary/runner.stderr.log &
echo $! > /tmp/phase3f-canary/runner.pid
```

Watch the first 60 seconds for the lifecycle four-tuple — read
straight from the bundle, do not `cat` the launcher stdout (which will
print Nautilus traces):

```bash
RUN_ID=$(ls -t data/testnet | head -1)
echo "RUN_ID=$RUN_ID"
tail -f data/testnet/"$RUN_ID"/logs/runtime.log
# Expect: credentials_loaded → node_built → node_run_invoked →
#         strategies_registered (strategies=1)
# Ctrl-C the tail once strategies_registered shows up.
```

If `strategies_registered` does not appear within 30 s, **stop** (§7)
and inspect `/tmp/phase3f-canary/runner.stderr.log`.

---

## 6. Monitor the session

Run these in a third terminal. The session is 6 h; check at minute
1, 5, 15, then hourly.

```bash
RUN_ID=$(ls -t data/testnet | head -1)
B="data/testnet/$RUN_ID"

# Last heartbeat
tail -1 "$B"/logs/heartbeat.jsonl | jq .

# Alert log — file MUST NOT exist for a "clean" session
ls -la "$B"/logs/alerts.log 2>/dev/null || echo "no alerts (good)"
[ -f "$B"/logs/alerts.log ] && cat "$B"/logs/alerts.log

# Watchdog last state
cat infra/watchdog/state.json

# Nautilus ERROR / WARN count
grep -c ERROR /tmp/phase3f-canary/runner.stdout.log
grep -c WARN /tmp/phase3f-canary/runner.stdout.log

# Sidecar growth (orders / fills)
ls -la "$B"/*.parquet 2>/dev/null
```

If any of these go bad mid-session, jump to §7.

---

## 7. Emergency stop

If anything looks wrong — runaway PnL, unexpected order activity,
watchdog reporting `heartbeat_lost`, or simply needing to abort —
**flatten first, then kill the process**:

```bash
RUN_ID=$(ls -t data/testnet | head -1)
UV_CACHE_DIR=/tmp/uv-cache uv run python \
  -m apps.strategies_nautilus.runners.emergency_flatten \
  --kind testnet \
  --run-id "$RUN_ID" \
  --operator nishiki \
  --reason "operator-aborted first canary" \
  --instrument-id BTCUSDT.BINANCE
```

Only after `emergency_flatten` returns `success: true` (exit 0) is it
safe to kill the runner:

```bash
kill -TERM "$(cat /tmp/phase3f-canary/runner.pid)"
sleep 5
kill -KILL "$(cat /tmp/phase3f-canary/runner.pid)" 2>/dev/null || true
kill -TERM "$(cat /tmp/phase3f-canary/watchdog.pid)" 2>/dev/null || true
```

Open `docs/retros/<UTC>-freqai-linear-v1-disable-after-canary-abort.md`
and record what happened. Promote-review will produce a `disable` or
`demote` retro depending on cause.

---

## 8. Clean shutdown after `max_duration`

The runner stops itself at `max_run_seconds`. Verify the manifest after
the process exits:

```bash
RUN_ID=$(ls -t data/testnet | head -1)
B="data/testnet/$RUN_ID"

jq '{
  shutdown_reason: .runtime.shutdown_reason,
  elapsed_seconds: .elapsed_seconds,
  git_dirty: .git_dirty,
  strategies_registered: .runtime.strategies_registered,
  enable_strategy_execution: .runtime.enable_strategy_execution,
  open_orders: .runtime.open_orders,
  open_positions: .runtime.open_positions,
  daily_pnl: .runtime.daily_pnl,
  exchange_error_count: .runtime.exchange_error_count,
  ws_reconnect_count: .runtime.ws_reconnect_count
}' "$B/run_manifest.json"

wc -l "$B"/logs/heartbeat.jsonl
ls -la "$B"/logs/alerts.log 2>/dev/null || echo "no alerts (good)"
ls -la "$B"/*.parquet 2>/dev/null

# Kill watchdog (it's still looping)
kill -TERM "$(cat /tmp/phase3f-canary/watchdog.pid)" 2>/dev/null || true
```

Then stop watchdog (§7 last block) and move to §9.

---

## 9. Write the session retro

Copy the template at
`docs/templates/testnet-canary-session-retro.md` to a real retro
filename and fill in the captured numbers:

```bash
RUN_ID=$(ls -t data/testnet | head -1)
DATE=$(date -u +%Y-%m-%d)
cp docs/templates/testnet-canary-session-retro.md \
  "docs/retros/${DATE}-phase-3f-testnet-canary-session.md"

# Fill in placeholders, then commit + push.
```

The retro **must** record:

1. `run_id`, `git_commit`, `git_dirty`, `started_at`, `finished_at`,
   `elapsed_seconds`.
2. `shutdown_reason`, `auto_flatten_trigger`, `emergency_flatten_success`.
3. heartbeat count, alerts.log status, all 9 ADR-008 §5.4 alert kinds
   (silent vs fired).
4. Real order / fill / position counts from the sidecars, plus the
   first/last fill timestamps if non-zero.
5. The `freqai_linear_v1` signal flow during the session (rows polled,
   `cursor_ns` start/end).
6. Nautilus log error count and final account snapshot.

Once the retro is committed, decide via `promotion_review.py` whether
this experience supports a `hold @ testnet_canary` (keep going) or a
`demote/disable` (back to `paper_simulated`). Open the new retro for
that decision with `--paper-simulated-retro-path` and
`--testnet-runbook-signoff-path` (pointing now at the session retro you
just wrote, not the Phase 3f stability soak).
