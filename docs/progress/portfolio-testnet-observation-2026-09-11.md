# Full-account Spot testnet observations and native reconnect — 2026-09-11

Status: **real signed subscriptions, bounded full-account reads, explicit reconnect
and detached archive replay passed**. This follows the
[Ed25519 credential and initial account read](portfolio-testnet-ed25519-2026-09-11.md).
It does not qualify independent identity, API-key restrictions, a recovery baseline,
global user-stream continuity, or real adapter process recovery.

## Observation contract

`apps/strategies_nautilus/portfolio_testnet_observation.py` defines the explicit
`portfolio.testnet_observation.v1` profile. Its journal subclasses the existing
durable source-bound journal, but refuses strict collector anchor metadata and
strict evidence sealing. It returns summary dictionaries, never `CollectedAccount`
or a reusable recovery fence. The strict `/sapi/v1/account/apiRestrictions`
requirement is unchanged. Spot testnet excludes `/sapi`; successful signed reads,
account `canTrade`, and signed subscriptions do not verify API-key trading restrictions.
Results retain `api_trading_enabled=null`, `api_key_restrictions_verified=false`
and `runtime_ready=false`.

A selected initial observation requires an exact artifact SHA256, the testnet
endpoint, the current API-key fingerprint and its raw response hash. Its observed
UID becomes the consistency reference for subsequent reads, explicitly with
`independent_uid_verified=false` and `baseline_qualified=false`.

Each collection makes four signed GETs in order:

1. `/api/v3/account?omitZeroBalances=false`
2. `/api/v3/openOrders` without a symbol selector
3. `/api/v3/openOrders` without a symbol selector
4. `/api/v3/account?omitZeroBalances=false`

Raw responses and unsigned selectors are persisted before parsing. Both full
account bodies and both open-order lists must agree exactly; this is a stable
observation check, not an atomic exchange revision. Asset names retain Unicode;
all free/locked asset rows and account-wide orders remain in the archive. No
BTC/USDT projection, valuation or synthetic 500 USDT substitution occurs. Duplicate
assets/orders, bad quantities, changed UID/key, drifting responses, connection
changes, events, concurrent collections and clock regression fail closed.
The existing 60-second collection timeout/abort lifecycle is reused. Synchronous
disk I/O is not preempted by async timeouts.

The testnet journal retains source-bound fresh envelopes for
`outboundAccountPosition`, `balanceUpdate`, `executionReport`, `externalLockUpdate`
and `listStatus`. It records raw receipts only: recognizing an event name does
not qualify the financial payload, patch native balances or infer fills/cash flows.
Every receipt, including duplicates, invalidates in-flight collections. Unknown
or terminal event kinds are retained when their envelopes pass source/time checks,
then the subscription is invalidated. Malformed/foreign/stale frames fail closed.
The existing 64 KiB frame bound and dedicated strict journal behavior are unchanged.

Local replay pins the whole archive digest, validates the hash chain/source,
subscription epochs, selected profile, timestamps, request order, raw response
hashes and completion marker. Interrupted/aborted collections cannot replay as
completed. Rehashed malformed sequences still fail semantic checks. An archive
hash is a local integrity reference, not independent venue authentication or a
proof that no historical events were omitted.

## Bounded operations entrypoint

`apps.ops.portfolio_testnet_observe` loads only the explicit Ed25519 configuration
and selected initial observation. It exclusively creates a new 0600 archive,
starts two separate signed native WebSocket subscriptions, takes observations
before/after two five-second ping intervals in each, and closes both connections.
It checks that disconnect invalidates the fence, reconnect creates a different
epoch and the old fence remains unusable. Total async session time is bounded to
180 seconds plus bounded cleanup; failures retain the partial archive and do not
automatically retry. The closed archive is replayed before success is reported.

Example for a new explicitly selected observation run (the archive must not exist):

```bash
.venv/bin/python -m apps.ops.portfolio_testnet_observe \
  --credentials /home/orca/.config/trader/binance_testnet.env \
  --selection data/spot-testnet-initial-account-20260911T014024Z.json \
  --selection-sha256 205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc \
  --archive data/spot-testnet-observation-new.jsonl
```

## Real external evidence

The September 11 run used `https://testnet.binance.vision` and
`wss://ws-api.testnet.binance.vision/ws-api/v3`, through the existing project-owned
native HTTP/WS signers and Rust WebSocket I/O. The journal spans **23.806 seconds**:

| Observation | Result |
|---|---|
| Signed subscriptions / distinct local epochs | 2 / 2 |
| Completed collections / signed GETs | 4 / 16 |
| Asset records / nonzero assets in every collection | 502 / 502 |
| Account-wide open orders in every collection | 0 |
| Application ping confirmations | 6 |
| Account event envelopes received | 0 |
| Explicit reconnect and old-fence rejection | Passed |
| Closed archive replay, including another fresh process without credentials | 4 / 4 passed |

The quiet session proves transport responses during this bounded interval; zero
business events cannot establish delivery completeness, execution-event parsing,
downtime history or real native adapter state reconstruction. Explicit reconnect
is not abrupt full-process recovery. These remain false in the run summary.

Private local evidence is ignored by Git and was created with mode 0600:

```text
data/spot-testnet-observation-20260911T015529Z.jsonl
SHA256: d1f437b5e9ee4a38f6c53cc20ca4dc73c6e8cfa587cfc2e52efa76c653ca875d
data/spot-testnet-observation-20260911T015529Z-summary.json
SHA256: ba129849e8c0d7788486b4860acbfb28550150b7064eb614aedc3896895ab5f6
```

Selected collection IDs, in order:

```text
26708dad-069b-46d6-a6f7-fc9620dd6592
0aebdd0a-ff16-46b2-b478-ff328fbe4f44
7f5d98ec-53ac-4de8-8aff-b7dd50d60fb2
185007e9-d583-46dc-b16e-5dc78f0214d0
```

No secret values, full private responses or UID values are included in tracked docs.
The original initial observation and credentials remain unchanged.

## Verification and next qualification

49 new offline tests cover all assets/Unicode, invalid balances/orders, source and
clock changes, interrupted collections/retry, raw events/termination, strict-gate
separation, archive corruption/semantic tampering, reconnect, exclusive files,
cleanup and private-error suppression. Full offline regression: **2,262 passed,
12 Postgres integration tests deselected** (60.35 seconds). Ruff, the research
family registry and whitespace checks passed. Upstream checkouts, installed packages, execution runners,
SourcePolicy and live trading paths are untouched; no order/cancel request or
strategy startup occurred.

Next establish an independently corroborated UID and full-account baseline with
explicit faucet/reset semantics and supported permission evidence. Testnet's
missing restrictions API remains unknown rather than bypassed. Then qualify real
business-event handling, downtime/history coverage, native account/asset mapping
and fresh-process adapter recovery under that full-account contract. The 502-asset
account is incompatible with the dedicated synthetic flat BTC/USDT anchor. Keep
the planning 50 USDT daily loss versus binding 5% rule unresolved until explicit
policy reconciliation; these observations cannot clear it.

Official references consulted:

- [Testnet general information](https://developers.binance.com/docs/binance-spot-api-docs/testnet/general-info)
- [Testnet user data stream (including Unicode names)](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/user-data-stream.md)
