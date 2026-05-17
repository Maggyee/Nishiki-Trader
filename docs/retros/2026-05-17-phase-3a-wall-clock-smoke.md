# Phase 3a wall-clock paper runtime — first real-WS smoke

- **Date (UTC)**: 2026-05-17
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.1](../decisions/008-phase3-risk-runbook.md) Phase 3a (wall-clock paper without credentials)
- **Kind**: Implementation milestone retro — not a `SourcePolicy` decision. No
  source / model_version was promoted, held, demoted, or disabled.

## 1. Scope

ADR-008 §6.1 introduces a `--data-mode wall_clock` to the existing
ADR-007 paper runner. Instead of replaying a static `catalog_polling`
bar list, the runner streams closed 1m klines from a Binance public WS
endpoint (no API key, no testnet, no exchange-adapter), funnels them
through the same per-bar simulator, and writes a `kind="paper"` bundle.

Phase 3a is **runtime mechanics only**. It does not:

- Read any `BINANCE_*` environment variable.
- Connect to testnet or any private endpoint.
- Submit any live order.
- Open any exchange adapter credential path.

## 2. Code surface

- `apps/strategies_nautilus/runners/wall_clock_bar_feed.py` — new module.
  Implements `BarFeed` Protocol, `BarSample` dataclass, and
  `BinancePublicBarFeed`, which wraps NautilusTrader's
  `BinanceWebSocketClient` (Rust-backed pyo3 WS client). The wrapper:
  - constructs `BinanceWebSocketClient` with **no credentials** —
    `BinanceWebSocketClient.__init__` does not accept api_key/secret;
    public kline streams need none.
  - subscribes to `<symbol>@kline_<interval>` (default `btcusdt@kline_1m`).
  - parses each message; only emits closed klines (`k.x == True`).
  - dedupes by `ts_event_ns` (the kline close time → ns), tracking
    `duplicate_bars_dropped`.
  - increments `reconnect_count` via the `handler_reconnect` callback
    NautilusTrader's WS client fires on WS-level reconnect events.
  - exposes a thread-safe `next_bar(timeout)` over a `queue.Queue`,
    pushed from an asyncio loop in a daemon background thread.
- `apps/strategies_nautilus/runners/paper_runner.py` — refactor:
  - new `_StepState` dataclass + `_step_one_bar` helper. The
    catalog_polling simulator and the new wall_clock simulator share
    one per-bar code path so their bundles use identical fingerprint
    semantics (orders/fills/positions/lineage/heartbeat/account rows).
  - new `_simulate_paper_wall_clock` orchestrates the pull-loop:
    SIGTERM/`stop_event`, `--max-duration-seconds`, `--max-bars` are
    all explicit stop conditions; `signal_poll_interval_seconds`
    paces incremental SignalStore re-polls (so an upstream research
    job can write new signals while the runner is alive).
  - manifest `runtime` adds the wall-clock-specific fields:
    `bar_source`, `ws_endpoint`, `ws_stream`, `ws_reconnect_count`,
    `duplicate_bars_dropped`, `max_duration_seconds`, `max_bars`,
    `signal_poll_interval_seconds`, `shutdown_reason`,
    `credentials_loaded` (always false in this phase),
    `bar_count`.
  - `_resolve_runtime_context` skips `catalog_start` override when
    `data_mode="wall_clock"` (WS streams live data; there is no
    historical catalog cursor to seek).
- `tests/strategies_nautilus/test_wall_clock_paper_runner.py` — 13 unit
  tests covering: forbidden-token scan over both modules; closed-kline
  dedup; non-closed kline rejection; non-kline payload rejection;
  max-bars stop with manifest; reconnect-count propagation;
  duplicate-drop-count propagation; in-bar signal consumption with
  SignalStore; `_wall_clock_refresh_signals` cursor advance and
  idempotency; per-event-time heartbeat cadence; missing-stop-condition
  config rejection; SIGTERM stop_event; max-duration stop.

## 3. Smoke evidence

Real 5-minute WS run on home-frp against `wss://data-stream.binance.vision:9443`
(`stream.binance.com:9443` is unreachable from this network — DNS
resolves to a non-Binance IP). DNS for `data-stream.binance.vision`
resolves to a real Binance AWS Tokyo address (`52.199.12.217`).

- **bundle**: `data/paper/20260517-075403Z-b76dcdb1/`
  - `run_manifest.json` sha256: `f80bd450fa6e47287316aba90498244fe467f341a3af54bb5b570e4babf3f56d`
  - `orders.parquet` sha256: `8b58edea7acb515536135400857d05e08834fdef5ba72cb171842999fb0d6253`
  - `fills.parquet` sha256: `f06435a92ee54806396e49eecb8fc7b6d4cb333e60afc7c27dd733b4467084ab`
- **window**: `started_at=2026-05-17T07:54:03.270Z`, `finished_at=2026-05-17T07:59:03.458Z`
  (elapsed 300.19 s).
- **bars consumed**: `bar_count=5` (1m bars at 07:55, 07:56, 07:57,
  07:58, 07:59 BTCUSDT spot, last_price `78184.11 → 78176.60 →
  78164.67 → 78164.66 → 78170.01` USDT).
- **heartbeats**: 5 rows in `logs/heartbeat.jsonl`, one per closed bar,
  exactly 60 s apart by `ts_wall_clock`.
- **data gaps**: 0.
- **WS reconnects**: 0.
- **Duplicate bars dropped**: 0 (5 min is too short to expect WS
  retransmission noise; dedup path is exercised by the unit test
  `test_binance_public_bar_feed_dedupes_by_ts_event_ns`).
- **Shutdown**: `shutdown_reason="max_duration"` — clean stop on the
  `--max-duration-seconds 300` deadline.
- **Credentials**: `runtime.credentials_loaded=false`. CLI was invoked
  with `--policy-dry-run`, no API-key env vars in the parent shell.
- **Lineage / orders / fills**: empty (signal store was an empty
  temp DB so authorization had nothing to evaluate). The simulation
  path itself is well-exercised by the catalog_polling suite; this
  smoke only validates the bar-feed plumbing.

Manifest `git_dirty=true` because the smoke ran against an uncommitted
working tree. The first committed wall-clock bundle will land with
`git_dirty=false` and a real `git_commit` matching this PR.

## 4. ADR-008 §7.2 checklist status

| §7.2 item | Status | Evidence |
|---|---|---|
| 1 — `--data-mode wall_clock` reads no `BINANCE_*` env vars | ✓ pass | `test_wall_clock_sources_have_no_credential_or_live_tokens` greps both `paper_runner.py` and `wall_clock_bar_feed.py`; smoke manifest `credentials_loaded=false` |
| 2 — WS reconnects within N seconds | ⏸ structural | NautilusTrader's pyo3 WS client owns reconnection; `handler_reconnect` increments `ws_reconnect_count` and the manifest carries it (asserted by `test_wall_clock_paper_session_propagates_reconnect_count`). Real reconnect timing TBD by the 24h soak — 5 min smoke saw 0 reconnects. |
| 3 — duplicate bars deduped by `ts_event_ns` | ✓ pass | `BinancePublicBarFeed._handle_message` skips any kline whose `T`-derived ts ≤ `last_emitted_ns` and increments `duplicate_bars_dropped`. `test_binance_public_bar_feed_dedupes_by_ts_event_ns` and `test_binance_public_bar_feed_ignores_unclosed_klines` exercise the path. |
| 4 — 24h continuous, one heartbeat per hour, no `data_gap` | ⏸ deferred | Heartbeat cadence verified at 1-minute resolution over 5 minutes (5/5 bars, 0 gaps); operational 24h soak is a separate ADR-008 §6.1 acceptance item and will be its own retro. |

## 5. Non-goals reconfirmed

- ADR-008 §6.2–§6.5 (testnet adapter, emergency flatten + kill-switch,
  restart REST reconciliation, alerts → exit codes) are **not**
  implemented. The `phase_3_not_ready` gate in `promotion_review`
  remains closed; no source can be moved beyond `paper_simulated`.
- No real exchange credentials touch the repo, the runtime, or this
  bundle. `runtime.credentials_loaded` is hard-coded false and
  `--allow-real-credentials` does not yet exist as a CLI flag.
- ADR-001 five iron rules untouched. ADR-002 SignalEvent v1 schema
  untouched. ADR-006 `SourcePolicy` fields untouched.

## 6. Follow-ups

1. Operational 24h wall-clock soak with a real (or extended-empty)
   SignalStore. Capture: `data_gap_count`, `ws_reconnect_count`,
   `duplicate_bars_dropped`, heartbeat gaps, any unexpected
   `shutdown_reason`. Land as `docs/retros/<UTC>-phase-3a-wall-clock-24h-soak.md`.
2. ADR-008 §6.2 Phase 3b: new `testnet_runner.py` with the §4
   credential-loading + `--allow-real-credentials` double-sign and the
   §4.2 startup checks.
3. Consider an idle-tick wall-clock heartbeat (driven by wall clock,
   not bar event time) so a multi-hour WS outage still leaves a
   detectable heartbeat trail for the future watchdog. Phase 3a does
   not require it — bar-driven heartbeats give the §7.2 cadence when
   WS is healthy — but it is the natural next safety improvement.
