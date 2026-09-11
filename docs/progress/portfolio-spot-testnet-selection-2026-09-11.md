# Binance Spot testnet selected for read-only acceptance — 2026-09-11

The operator selected **Binance Spot testnet** for the next account/source and
recovery acceptance. This selects the environment for the existing read-only task;
it does not start a strategy, place testnet orders or resume the demoted legacy
canary identity. Production is not the selected environment.

## Verified inputs and compatibility

- REST: `https://testnet.binance.vision`.
- WebSocket API: `wss://ws-api.testnet.binance.vision/ws-api/v3` (the existing
  transport explicitly uses the equivalent port 443).
- A bounded unauthenticated `GET /api/v3/time` returned HTTP 200 with a
  `serverTime` field from this workspace. This verifies public REST reachability
  only; it does not verify signed requests, clock skew, UID, permissions or WS.
- The documented local credential reference is
  `~/.config/trader/binance_testnet.env`, with `BINANCE_TESTNET_API_KEY` and
  `BINANCE_TESTNET_API_SECRET`. The file was absent under the current user's home,
  and neither named variable was populated in the tool process. Only existence
  and boolean presence were inspected. No secret contents or other paths were read.
- Expected UID and an independent current account baseline remain unspecified.

The official [Spot testnet general information](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/general-info.md#faq-supported-endpoints),
retrieved on 2026-09-11, explicitly says:

> No, only the `/api` endpoints are available on the Spot Test Network.

The current strict `BinanceReadOnlyAccountCollector` requires
`/sapi/v1/account/apiRestrictions`. Testnet permissions support is therefore a
confirmed interface incompatibility, replacing the earlier unknown-availability
status. Do not send a futile signed SAPI probe, switch to production, synthesize a
permission response, or treat account `canTrade` as proof of API-key restrictions.

The same official document states that testnet allocates virtual balances in many
assets and periodically resets balances and order history. The current detached
reconciliation fixture assumes a dedicated BTC/USDT account with a flat independent
baseline. A faucet account cannot be qualified by discarding other assets or
substituting the provisional 500 USDT budget. A reset invalidates prior baseline
and continuity assumptions and requires fresh evidence.

## Next implementation and operator inputs

Implement an explicit testnet **observation** profile using supported signed `/api`
account reads and the existing source-bound user stream. Preserve raw responses,
full account assets and account identity, while marking unavailable API-key
restriction evidence as unknown. The existing strict reconciliation gate must not
accept that observation as a completed permission-qualified account collection.
This profile is not implemented by this documentation change.

Before private reads, the operator must supply the testnet credential reference,
expected UID, and current baseline evidence (time and all asset balances). The
documented conventional path can be used; if another path is intended, specify it.
No key or secret value should be sent in chat. The old canary documentation expects
Ed25519, whereas the new read-only transport's independent signature acceptance
currently covers HMAC; confirm the selected key type and verify the corresponding
native signing path before relying on it.

Once those inputs and the observation profile exist, run bounded signed account
and WS observations, archive/replay them, and qualify the native reconciliation
mapping against the actual testnet account. Existing offline recovery results
cannot substitute for this external evidence. Historical canary evidence remains
archived under `phase-3-testnet-canary-evidence.md` and authorizes no new order run.

## Change verification

Only the environment selection, verified blocker and current next steps were
documented. Public documentation retrieval and the unauthenticated time request
succeeded; credential-reference presence checks returned absent. `git diff --check`
passes. No code changed, so no new tests or full-suite rerun were needed. The prior
offline result remains 2,194 passed, 12 PostgreSQL tests deselected.

No upstream source, execution runner, account checkpoint, SourcePolicy, schedule,
5% risk rule or live trading path was changed. No private account was accessed.
