# Phase 3b Binance Spot testnet connection probe — first run

- **Date (UTC)**: 2026-05-18
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.2](../decisions/008-phase3-risk-runbook.md) Phase 3b
- **Kind**: Runtime acceptance retro — not a `SourcePolicy` decision. No
  source / model_version was promoted, held, demoted, or disabled. The
  promotion `phase_3_not_ready` gate stays closed; §6.3 (emergency_flatten /
  kill-switch), §6.4 (restart reconciliation), and §6.5 (alerts) remain.

## 1. Scope

This retro records the first end-to-end Binance Spot **testnet** connection
exercised by `apps/strategies_nautilus/runners/testnet_runner.py --connect-probe`.
The probe was driven only by ADR-008 §4 startup gates plus the new probe
path: it built a real `nautilus_trader.live.node.TradingNode` with a
credentialed `BinanceDataClientConfig` + `BinanceExecClientConfig`
(`environment=TESTNET`, `account_type=SPOT`), registered
`BinanceLive{Data,Exec}ClientFactory`, called `node.build()` and `node.run()`
with **zero strategies and zero actors registered**, stopped after 30s via
a background `loop.call_soon_threadsafe(node.stop)` timer, and disposed.

The probe is by construction unable to submit any order: the registered
trader has empty `strategies` and `actors` lists, asserted both at unit-test
time and recorded in the bundle (`strategies_registered=0`,
`actors_registered=0`). No live mainnet credentials were ever read; the
runner source contains no `BINANCE_API_KEY` or `BINANCE_API_SECRET` symbol
(grep-asserted by `test_testnet_runner_does_not_reference_live_binance_credentials`).

## 2. Run identity

- bundle: `data/testnet/20260518-122839Z-24bf3db2/`
- run_id: `20260518-122839Z-24bf3db2`
- git_commit: `d9e542b00e1e741f6a5a6fe6d3bdc3cec9814a8c`
- git_dirty: `false`
- started_at: `2026-05-18T12:28:39.287Z`
- finished_at: `2026-05-18T12:29:14.572Z`
- elapsed_seconds: `35.285106`

## 3. Runtime counters

| metric | value |
|---|---|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| exchange | `binance` |
| exchange_endpoint | `https://testnet.binance.vision` |
| ws_api_endpoint | `wss://ws-api.testnet.binance.vision/ws-api/v3` |
| account_type | `SPOT` |
| environment | `TESTNET` |
| credentials_source | `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET` |
| credentials_key_prefix | `yKtnt9cb` (8 chars only; full key never written to disk) |
| credentials_key_type | Ed25519 (PEM-PKCS#8 secret, auto-detected by Nautilus) |
| max_connect_seconds | 30.0 |
| stop_reason | `max_duration` |
| node_built | `true` |
| node_run_invoked | `true` |
| strategies_registered | 0 |
| actors_registered | 0 |
| error | `null` |

## 4. Connection timeline (from Nautilus logs)

| relative time | event |
|---:|---|
| T+0.000s | probe `credentials_loaded` event written |
| T+0.123s | `node.build()` complete (`node_built` event) |
| T+0.124s | `node.run()` invoked (`node_run_invoked` event) |
| T+0.131s | DataEngine / RiskEngine / ExecEngine RUNNING |
| T+0.132s | TradingNode: Awaiting engine connections (30.0s timeout) |
| T+0.133s | ExecEngine: Awaiting startup reconciliation |
| T+0.615s | **`Account BINANCE-SPOT-master registered in cache`** (session.logon Ed25519 succeeded; account state pulled) |
| T+0.885s | TradingNode: Awaiting execution state reconciliation (10.0s timeout) |
| T+0.960s | ExecEngine: Reconciling ExecutionMassStatus for BINANCE |
| T+0.962s | **`Reconciliation for BINANCE succeeded`** |
| T+0.962s | **`Execution state reconciled`** |
| T+0.962s | ExecEngine: Startup reconciliation completed |
| T+30.0s | timer fires `loop.call_soon_threadsafe(node.stop)` |
| T+~35.3s | TradingNode DISPOSED, all engines disposed |

## 5. What was verified

- ADR-008 §4 startup gates all passed: `--mode testnet`, `--kind testnet`,
  `--allow-real-credentials`, 64/64 credential lengths, clean git on commit
  `d9e542b`, paper_simulated retro evidence
  (`docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md`),
  `position_pct_multiplier=0.2`.
- The credentialed `TradingNodeConfig` carried real Ed25519 credentials in
  memory only — `embedded_credentials=false` in audit view, no key/secret
  appears in `connection_probe.json`, `logs/runtime.log`, or any other
  on-disk artifact in the bundle. Only `credentials_key_prefix=yKtnt9cb`
  (8 chars) is recorded.
- DataClient connected to Binance Spot testnet REST + WS.
- BinanceUserDataWebSocketClient connected to
  `wss://ws-api.testnet.binance.vision/ws-api/v3`.
- ExecClient `session.logon` succeeded under Ed25519; account state was
  pulled (10000 USDT / 1 BTC / 1 ETH and other testnet faucet balances).
- ExecutionMassStatus reconciliation succeeded; startup reconciliation
  completed; no orders, fills, or positions existed because no strategy
  was registered.
- Background timer cleanly stopped the node at the 30s budget; full
  disconnect / dispose path completed without errors.
- No `Error on '_connect'` for either DataClient or ExecClient in the
  Nautilus log. Total `ERROR` count = 0.

## 6. Earlier attempts (kept as evidence of error-path behaviour)

The probe code itself was first exercised against misconfigured
credentials. Both attempts demonstrate that the probe **never crashes,
never leaks credentials, and always writes a clean bundle** even when
the upstream auth path fails. Bundles retained under `data/testnet/`
(gitignored) for local inspection only.

- bundle `20260518-121406Z-d4b2147b` — env file accidentally contained
  the `<...>` template markers around the value, so the effective key
  started with `<`. Binance returned
  `BinanceClientError({'code': -2014, 'msg': 'API-key format invalid.'})`
  on ExecClient `_connect`. Probe: `stop_reason=max_duration`, `error=null`,
  `node_built=true`, `node_run_invoked=true`.
- bundle `20260518-121555Z-e4290f84` — HMAC key with correct length.
  Binance returned
  `RuntimeError(Request session.logon failed: HMAC-SHA-256 API key is not supported.)`.
  This is a Binance Spot testnet WS API constraint, not a Nautilus or
  trader-code bug: `nautilus_trader.adapters.binance.execution._connect`
  unconditionally calls `session_logon()`, and Binance Spot WS API
  `session.logon` accepts only Ed25519. Probe: `stop_reason=max_duration`,
  `error=null`, `node_built=true`, `node_run_invoked=true`.
- bundle `20260518-121657Z-d3adf077` — same HMAC failure with
  `--max-connect-seconds=5`, used purely to capture the full Nautilus
  error message for diagnosis.

The Ed25519 key for the successful run was generated locally with
`openssl genpkey -algorithm ed25519` to
`~/.config/trader/binance_testnet_ed25519.pem` (perm 600); only the
public key was uploaded to Binance. The private PEM is loaded into
`BINANCE_TESTNET_API_SECRET` via
`"$(cat ~/.config/trader/binance_testnet_ed25519.pem)"` in
`~/.config/trader/binance_testnet.env`, so the secret never persists in
the env file itself.

## 7. Open items / follow-ups

- The probe summary field `startup.exchange_connected` is a
  validation-time snapshot and stays `false` even after a successful
  connect. Runtime connectivity must be assessed from Nautilus logs
  (look for `Account BINANCE-SPOT-master registered in cache` and
  `Reconciliation for BINANCE succeeded`). A future refinement could
  promote a runtime-level connectivity bool into the summary.
- ADR-008 §6.3 (emergency_flatten + kill-switch), §6.4 (restart
  reconciliation), §6.5 (alerts) are still required before the
  `phase_3_not_ready` gate can be relaxed for any `paper_simulated →
  testnet_canary` promotion. This probe is a **connection-only**
  exercise, not a stage promotion.
- The previously-leaked HMAC testnet key (`ToksJlCe...` prefix) and the
  Ed25519 API key used here (`yKtnt9cb...` prefix) are operator-managed.
  Operator action item: rotate / delete on the Binance testnet console
  after this retro is committed, then either regenerate or leave the
  account empty until §6.3 work begins.
