# Post-v27 authority and capacity review

Date: 2026-09-25. Scope: offline review of retained evidence only. Decision:
**real joint collection remains blocked before its first request**. This review
does not open a scope, select a key, contact a venue or qualify trading.

## Evidence checked

| Retained input | SHA256 | Relevant result |
| --- | --- | --- |
| [v27 fixture acceptance](portfolio-installed-joint-complete-acceptance-2026-09-25.json) | `c5052c5fe67a879cf90d1a4e3c178c7c20a4961954c49eb4ae8b8efdaaa380e2` | 19/19 fixed operations; four fixture assets reconcile; real account interval, stream fence, source coverage and provider clock remain false. |
| Ignored `data/spot-testnet-observation-plan-20260913.json` | `0a00f4d27a8bc0377ef34c2b888f9e99ffb564a4ce384f0cbdd5a33cf529ca8f` | Historical 502-asset account, three selected route symbols and 499 full-route symbols. Original inputs and planning method are described in the [design](portfolio-testnet-joint-observation-design-2026-09-13.md). |
| Ignored `data/spot-testnet-baseline-gap-review-20260913-v2.json` | `254fac56d653ff797d9e3039d62a76735f98ceffc8f135ebc7019fc0255` | Historical balance bridge completes, but baseline qualification is false; see the [gap review](portfolio-testnet-baseline-gap-2026-09-13.md). |
| [Consumed public bootstrap](portfolio-egress-bootstrap-result-2026-09-16.json) | `728423996181c63e4a1f940fcdaf1c7c8d5df5c63432979478f1ad90a0433a77` | One GET returned a historical 6,000/minute limit and post-request weight count 20; RAW_REQUESTS usage, connection attempts and future coverage remain unknown. |
| [Bootstrap-to-joint review](portfolio-bootstrap-joint-review-2026-09-16.json) | `8921316cc1fee1dd23c1e0c50eb891b5e12cd9db4cc1439950ba2d71642e3a78` | Header-to-body completion took 7.822518713 seconds versus the five-second sample age limit. No qualified clock interval, authenticated initial source or complete egress candidate exists. |
| [Frozen prospective joint contract](portfolio-testnet-joint-capture-contract-2026-09-14.json) | `91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48` | Maximum 17 GETs, 468 documented weight, 21 durable preparations; this is a draft, not an active permit. |

The ignored historical files were inspected by hash and selected summary fields;
they were not copied into git. The v27 fixture operation count is not a budget for
the separate 17-GET real draft. Its 79 sampled spare descriptors also cannot
predict the memory, descriptor use or throughput of 502 assets/499 streams.

## Capacity and coverage decision

The historical three-symbol pilot covers BTC, ETH and BNB's routes, plus USDT
without a market leg. **496 assets remain outside those route symbols**, two
nonzero assets have no price path, and 65 exceed a historical top-book conversion
leg. Three pilot routes therefore cannot be relabelled full-account equity.
The historical 499 route symbols cost 2,495 depth weight at 100 levels or
124,750 at 5,000 levels; including the earlier joint-observation overhead gives
2,928 or 125,183 respectively. Only the former fits the historical 6,000/minute
limit arithmetically, before other callers, and neither establishes sufficient
book liquidity, full quote freshness, account/market revision alignment or
consumer throughput. These are historical calculations, not current allowances.

The one-shot bootstrap source mapping used an operator console copy matching
local metadata and a verified remote TLS connection. There was no independent
venue public-source echo or continuously enforced all-caller history. Its guard
ended after the consumed GET. The [offline joint reviewer](portfolio-bootstrap-joint-review-2026-09-16.md)
already refuses reuse: the header counter is stale by body completion; the
reported `serverTime` is not a qualified offset interval; REST RAW_REQUESTS,
account WS and market connection usage, failed/uncertain attempts and competing
callers through the 125-second horizon lack bound evidence. The market connection
weight charge is unresolved. No local fixture or hash of a self-reported candidate
authenticates that history. Reopening the consumed bootstrap or depth scopes would
not fill these gaps.

Even with a future admissible bounded capture, provider documentation has no
common account/market revision, durable user-event replay cursor or documented
testnet reset history. Two unpriced assets and independent UTC day-open, peak and
flow/reset evidence remain separate blockers under ADR-015/016. Qualified equity
and daily/peak loss inputs stay null; strict testnet continuity remains 0/14.

## Next implementation boundary

First specify and test a **prospective authenticated source and egress evidence
adapter** against the installed gateway: fixed root-owned code and dedicated UID,
destination/source and address-family bindings, complete applicable pre-dispatch
intervals including failed/uncertain attempts, and enforced other-caller bounds
through shutdown. Keep separate REST, account WS and market records; reject drift,
gaps and unknown charges. Reuse the existing offline admission and reservation
reviewers for arithmetic, with independent fixture and crash/expiry acceptance.
This is an offline implementation entrypoint, not a request to install a guard or
perform another host interruption.

Then establish fresh authenticated rates and provider clock bounds inside a
separately reviewed prospective scope, resolve market connection charges, and
bind each dispatch to durable remaining-budget reservations. Only after those
gates and full-asset coverage are independently reviewed should a distinct real
one-shot profile be considered. The old fixed-session BUY/cancel and public
bootstrap remain consumed; no trading or production execution permission follows.

Verification: original tracked hashes and the two ignored report hashes above
were rechecked locally; selected JSON status/capacity fields were inspected with
`jq`. No test suite was run for this documentation-only review. No upstream source,
network path, risk policy, credential or live order path was changed.
