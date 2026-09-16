# Actual one-shot public REST bootstrap result

Date: 2026-09-16. **Completed; fixed scope consumed permanently.**

The operator-approved request ran from clean, pushed commit `471752c` using
root-owned pinned code and a protected plan. It made exactly one unsigned public
`GET https://testnet.binance.vision/api/v3/exchangeInfo`, with one TCP connection,
one verified TLS 1.3 handshake and no retry, redirect, private request or order.
GET preparation was recorded at **09:34:12.116582 UTC**. The response was **HTTP 200**,
with **2,495,288 body bytes** retained before interpretation. Original plan, journal,
wire response and all evidence hashes are in the [result JSON](portfolio-egress-bootstrap-result-2026-09-16.json).
The [accepted contract](portfolio-shared-egress-bootstrap-2026-09-16-v2.json) and
[preparation report](portfolio-egress-host-bootstrap-2026-09-16.md) remain historical.

## Restoration and original evidence

From the recorded window activation to final cleanup took **8.376638094 seconds**.
The preparation-to-cleanup interval, which includes activation overhead and bounds
the actual blackout, was **8.398201882 seconds**, below the authorized 20 seconds.
Collector operation completed within its 12-second permission. Cleanup recorded no
errors. Independent before/after comparison found **no changed structural network
fields**, excluding only known counters/lifetimes. Owned nft tables/FORWARD rules,
veth and namespace were absent. sing-box, Docker and tailscaled remained active.
No service restart was needed and no recurring guard/service was added.

Root-owned `/var/lib/trader/egress/rest-bootstrap-v1` retains the consumed scope.
Do not reset, delete, reopen or execute it again. The plan, events and response
were exported read-only to ignored private storage, then checked again against
original root bytes. Two fresh-process offline replays are byte-identical:
`9eac74c08e02c0e3f272b98e1e381684fe0ec76c7536823ae3b447c01a34388a`.
They reproduce one GET, TLS verification, chunk hashes, exact HTTP framing/body,
response rates and successful cleanup. No additional venue request was used for
verification. The unrelated installation acceptance record remains consumed.

## What the response establishes

| Field | Original response observation |
|---|---|
| REQUEST_WEIGHT | Limit 6,000 / minute; post-request count 20 |
| RAW_REQUESTS | Limit 300,000 / 5 minutes; usage unknown |
| ORDERS | Limits 50 / 10 seconds and 160,000 / day; usage unknown |
| Public source | Operator OCI mapping matched to IMDS/host; no venue public-IP echo |

The count of 20 is a response-time observation, not proof that earlier usage was
zero, a future reservation or full shared-source history. The parser's conservative
source/coverage/freshness admission flags remain false; TLS receipts are retained
separately and do not supply missing global quota authority. The new evidence
closes the single REST bootstrap step, not joint capture or trading readiness.

Next use these originals in the offline source/gateway and joint-admission review.
Complete prospective quota/caller coverage, authority and per-dispatch enforcement
are still required before a separately authorized joint capture. Preserve unknown
RAW_REQUESTS, connection usage, clock boundaries, account baseline and unpriced
assets. Do not substitute the snapshot for a current reservation or silently
repeat collection. The frozen joint draft stays **17 GETs / 468 weight** with SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.

Verification: 533 focused tests, final exact-source disposable normal/crash
acceptance, successful actual capture, structural restoration and two independent
replays. Source pins, formatting, local links and diff checks pass. Full application
regression was not rerun. Host reboot/power-loss and storage rollback remain
unqualified. Upstream source and live order paths were not touched. Prior ADR-017
and public-depth scopes remain consumed; strict continuity stays **0/14**.
