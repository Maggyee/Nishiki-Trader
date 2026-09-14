# Joint capture rate evidence and prospective contract — 2026-09-14

The rate evidence review resolves an ambiguity in the prior loopback milestone:
Binance publishes IP weight usage and connection **limits**, but the reviewed
sources do not document a pre-connect global connection-attempt usage interface.
A process-local counter cannot establish all clients' usage on a shared egress.
The new offline parser preserves this distinction and the separate draft capture
contract identifies what still blocks the first external dispatch.

The machine-readable [contract](portfolio-testnet-joint-capture-contract-2026-09-14.json)
has SHA256 `91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
Its proposed profile is `portfolio.testnet_joint_observation.v1`. It is not an
implemented profile, activation record or permission to run a probe. The original
synthetic and loopback profiles and consumed public v1/v2 and ADR-017 scopes stay
unchanged. This increment made no exchange request and loaded no credentials.

## Official evidence

All five official sources from the September 13 provider manifest were fetched
again from GitHub at revision `b8a0f61e088c65d18a157f2e11a8e273826b6c08`;
all byte lengths and SHA256s match. This rechecks pinned documentation, not current
venue limits. Original retrieval timestamps remain historical in the new manifest.

| Original source and section | What it establishes | What remains unknown |
|---|---|---|
| [REST, IP Limits](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/rest-api.md#ip-limits), lines 143–153 | `exchangeInfo.rateLimits` defines limits; `X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)` reports current IP weight. IP, rather than key, is the scope. | The response does not identify the public egress IP or reserve future capacity. `RAW_REQUESTS` usage is not a weight count. |
| [WS API, rate limits](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/web-socket-api.md#rate-limits), lines 384–438 and 507–521 | 300 connection attempts / five minutes / IP; top-level response `rateLimits` supplies counts; multiple intervals apply; connecting costs two weight. Weight is shared by connections from the IP. | A successful connect does not prove available pre-connect capacity or disclose other clients. These passages do not establish a common market-WS / WS-API connection ledger. |
| [WS API, exchange information](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/web-socket-api.md#exchange-information), lines 1534–1565 | `result.rateLimits` includes a `CONNECTIONS` definition with limit 300 and interval five minutes. | The definition has no `count`; missing usage must not become zero. A post-connect count, if supplied, would still be too late to authorize that first connection. |
| [Market streams, limits](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/web-socket-streams.md#websocket-limits), lines 57–63 | 300 connection attempts / five minutes / IP, 1,024 streams per socket, five incoming control messages per second. | No current global attempt counter or explicit connection request-weight cost is specified here. Do not call an unspecified weight a measured zero. |
| [General information, restrictions](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/general-info.md#faq-restrictions), lines 50–59 | Query current limits regularly; testnet limits are generally similar to Spot. | A documented example of 6,000 is not a current sample. |

TLS hostname verification, the remote socket address and a peer certificate bind
the destination. They do not reveal the source address after NAT. The selected
UID/key also does not identify an IP. A generic public-IP lookup may use a different
route/address family and cannot supply destination-specific egress evidence.

## Implemented offline interpretation

`apps/strategies_nautilus/portfolio_rate_evidence.py` has two pure entrypoints:
`rest_rate_evidence(metadata_raw, header_pairs)` and
`ws_rate_evidence(raw, request_id=...)`. There is no CLI, credential reader, socket,
capacity reservation or execution integration. Original bytes must already exist.

REST interpretation requires the ordered response header pairs and that same
response's exchangeInfo body. Header casing is normalized only after duplicates
are checked. Every advertised REQUEST_WEIGHT interval must have exactly one
matching valid counter; extra unknown weight intervals fail rather than disappear.
RAW_REQUESTS, ORDERS and CONNECTIONS definitions retain unknown counts. The original
body hash and canonical ordered-header-pairs hash are retained; the latter is not
a claim of raw HTTP wire formatting or source authentication.

WS interpretation binds the exact request ID and successful response. The
top-level `rateLimits` carries observed counts; an exchangeInfo result's nested
`rateLimits` carries definitions. Their overlapping limits must agree. A nested
CONNECTIONS definition never supplies a zero count. If a top-level CONNECTIONS
count actually exists, it is retained as a reported value without assigning it
market-endpoint coverage or undocumented pre-connect semantics. ORDERS remains
account scoped. REST and WS reports remain separate even when their numbers match.

Multiple intervals, exhausted counters and missing non-weight usage stay explicit.
Malformed numbers, booleans, duplicate JSON keys, nonfinite values, unsupported
rate types/intervals, missing counters and oversized inputs fail. Parsing sets
source authentication, freshness, cross-endpoint ledger, connection coverage and
network admission to false. Hashes authenticate neither provider nor egress.

## Draft bounded scope

The proposed collector would retain the same selected initial UID/key/endpoint,
both full four-GET account collections, and same-run account → exchangeInfo →
bookTicker route fixation. Targets remain BTC/ETH/BNB with at most three distinct
symbols, one 100-level snapshot per symbol and no route substitution.

An **additional early all-symbol exchangeInfo GET** follows the initial time read,
before the account socket. It obtains current limit definitions before that
connection. It cannot replace the later route metadata because doing so would
change the original-input ordering. For three symbols, the draft therefore has
**17 GETs (eight private), 462 REST weight + six WS API weight = 468 documented
operation weight**, three WS API operations including connect, one market connect,
and **21 durable preparations**. Fewer frozen route symbols remove only their
snapshot GETs/weight. The old 16-GET / 448-weight loopback contract is unchanged.
468 is not a measurement of all provider charges or a proof of sufficient capacity.
Any unresolved applicable charge or ledger scope continues to block admission.

The prospective limits are 120 seconds capture plus one shared five-second close
allowance, 10 seconds per request and 15 seconds market bootstrap. The new profile
selects a **two-second linked observation**, keeping the five-second usage-age
rule. The earlier design's 20-second idle period cannot pass that rule without
extra budgeted samples. No heartbeat or hidden time request is added. Slow reads,
stale samples or clock-window boundaries abort; a short observation is not a
guarantee that the full run can finish within one accounting window.

Shared bounds remain 16 MiB / 4,096 pending receipts, one MiB per frame and 64 MiB
archive including a 4 KiB incident reserve. Dispatch and processing age both count.
The future single scope is consumed durably before its first external dispatch;
HTTP retry, snapshot retry, reconnect, fallback and a replacement attempt are zero.
418/429 responses and retry metadata are retained, then the attempt stops.

## Admission and source requirements still to implement

1. **Before even the first time GET**, require fresh pre-existing authenticated
   usage, current applicable limits and bound egress evidence. That request costs
   weight too. A new unbudgeted discovery probe cannot solve this requirement.
   If no such evidence exists, the collector must stop before network I/O. A
   separately scoped bootstrap policy would require a prospective contract change;
   this contract grants no exception and no bootstrap probe.
2. Bind independent gateway/network-control records to each actual destination,
   address family, public egress identity and capture interval. Complete connection
   coverage must include the preceding rolling 300 seconds and all callers during
   capture, including failed/uncertain attempts. Retain separate endpoint ledgers;
   also conservatively reserve their union against applicable bounds without
   claiming the provider merges them. Existing local attempt logs, a process lock,
   the user's absence of other trading, or waiting five minutes alone cannot
   establish this coverage. No gateway/service is installed by this work.
3. Before every dispatch, reserve the entire remaining capture plus bounded other
   callers' consumption in every applicable interval. RAW_REQUESTS and additional
   weight intervals cannot be ignored. Server counts are observations, not atomic
   reservations. Retain REST/WS scopes until explicitly bound; never overwrite one
   with another's counter. A full server-clock uncertainty interval must fit the
   same accounting bucket; a regressing count or crossed boundary is not an
   invented reset. The complete egress ledger can bound otherwise unavailable
   counters only when its coverage of their full interval is established.
4. Persist each transport's original handshake response, authority/path/port,
   peer address, certificate digest and TLS hostname-verification result. Bind
   them to durable preparation, receipt clocks and selected source. Retain raw
   REST headers/bodies and WS frames before parsing. Reject redirect, unbound proxy,
   fallback or egress drift. Never archive outbound signatures, API keys or private
   keys. Current account UID/key checks and one signed subscription epoch remain
   necessary but cannot qualify a global identity/continuity baseline.

Handshake provenance here comprises the WS HTTP Upgrade status and original
ordered response headers, together with TLS verifier configuration/result and
peer certificate digest. REST retains its HTTP response status/header pairs and
the same TLS connection metadata. Record precisely which original fields the
transport exposes; a normalized header map cannot stand in for original pairs.

The installed NautilusTrader **1.226.0** Python `WebSocketClient` interface exposes
connect/send/close and activity state, but no handshake response, peer address or
TLS evidence accessor (`nautilus_pyo3.pyi`, class WebSocketClient). The loopback
runner currently records successful connection state, not real raw handshakes.
This is a concrete integration blocker. A project-owned transport solution needs
its own TLS/provenance and callback/failure acceptance before actual capture;
changing upstream or silently relabelling loopback evidence is not a solution.

Next implement that source/provenance boundary and no-network refusal for missing
initial/egress evidence, then durable one-shot admission and separate profile
replay. Available complete egress records still need to be established; this
increment neither obtains them nor asserts their existence. The draft must pass
the remaining offline acceptance before any actual capture is considered.

## Verification and boundaries

The new parser has **48 passing offline cases**, including multiple intervals,
duplicate/case-variant headers, JSON and integer corruption, exhausted usage,
WS definition/status separation, unknown connection counts and distinct endpoint
scopes, plus **three draft-contract checks**. The JSON operation totals and
unchanged original budget are checked against the existing planner; the source
byte hashes are independently rechecked. The original pinned WS documentation
example reproduces count 70 and keeps admission false.
Full offline regression: **2,962 passed, 12 deselected in 324.15 seconds**
(`-m 'not network and not postgres'`). The Postgres integration cases have no
dedicated test DSN. Ruff for apps/tests/notebooks, changed-file formatting,
research registry and diff checks pass. `docs/project-status.md` records the result.

All six qualification flags remain false; qualified current/day-open/peak equity
and losses and the common account/market revision remain null. Strict continuity
remains **0/14**. No upstream, order path, SourcePolicy, schedule, runtime setting
or existing selected private artifact was changed. Progress and the reading index
are updated for the next implementation entrypoint.

Changed files: `apps/strategies_nautilus/portfolio_rate_evidence.py`,
`tests/strategies_nautilus/test_portfolio_rate_evidence.py`,
`apps/strategies_nautilus/README.md`, `docs/agent-reading-list.md`,
`docs/project-status.md`, and this report with its matching JSON contract.
