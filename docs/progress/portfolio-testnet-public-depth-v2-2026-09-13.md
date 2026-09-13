# Public depth v2 single-attempt result — 2026-09-13

The prospective v2 BTCUSDT diagnostic **completed**, producing **20 native
Nautilus QuoteTicks** from 21 raw depth frames. Two fresh processes replayed the
closed archive into byte-identical reports. This verifies one bounded, locally
linked market segment under the explicit v2 interpretation; account/market
atomicity, valuation, baseline, runtime and new-order qualification remain false.

The [v2 contract and reasoning](portfolio-testnet-public-depth-v2-contract-2026-09-13.md)
and implementation were committed and pushed as **`cf4612c`** before this attempt.
The checkout was clean and synchronized. The frozen JSON SHA256 is
`885a636f4fd2daf8dbd1282e47639bcc12e10db60d685f8d452e0eb664789a04`.
No implementation changes followed the probe. The contract's **one prospective
v2 attempt is consumed**; this result does not start a recurring collector or
permit another attempt under the same one-shot scope.

## Actual observation

The process started **2026-09-13 06:46:25.403302 UTC** and sealed at
**06:46:43.667930 UTC**, elapsed **18.264627 seconds** within the selected 20-second
collection budget. It made exactly five successful public GETs in the frozen
order, with total weight 28 and one native market WebSocket connection. No HTTP
retry, second snapshot, reconnect, private endpoint or order request occurred.
The advertised request-weight limit was 6,000/minute, and the final shared-IP
usage header was 28.

The 100-bid/100-ask snapshot had `L=1745166`. The first buffered event was
`U=u=1745166`, so it was obsolete. The next event was `U=1745167, u=1745168` and
therefore contained the next unseen ID `L+1`. V2 linked this exact-successor case;
subsequent updates reached `u=1745191` without an observed gap. The 21 raw frame
ages at local receipt ranged from **41.931649 to 44.460871 milliseconds**.
This is locally observed update linkage; it does not prove global provider delivery
completeness or the ages of every untouched depth level.

| Selected `/time` sample | RTT (ms) | Apparent offset interval (ms) |
| --- | ---: | --- |
| Initial | 152.447910 | [-45.630555, 107.817115] |
| After snapshot | 118.071901 | [-45.436005, 73.635896] |
| Final | 113.481998 | [-44.762682, 69.718796] |

All three passed the original 500 ms RTT and entire-interval ±250 ms bounds;
wall/monotonic drift, five-second quiet age and finite-depth checks also passed.
Server time was not substituted for depth E. The first native quote retains
`ts_event=1789281989010000000`, `ts_init=1789281989054460871`; the last retains
`ts_event=1789282003305000000`, `ts_init=1789282003348053720`. Snapshot arrival and
heartbeat receipts did not generate quotes or refresh their event times.

## Retained evidence and replay

The original archive has **175 rows / 108,283 bytes**, including intentional
transport closure and a successful completion seal. It uses a new epoch and
profile `testnet_public_depth_evidence_v2`. These artifacts remain ignored local
data; only this reviewed result and hashes are committed.

| Local artifact / derived evidence | SHA256 |
| --- | --- |
| `data/spot-testnet-public-depth-v2-20260913.jsonl` | `76d93c90028719907c40eaa870192bbf255af792a49131fabc4fd38b25f8d8aa` |
| `data/spot-testnet-public-depth-v2-20260913-report.json` | `ff847b78a5955329c73fc8be2cd4bb7cbb997780e0382fec036f96f05621e977` |
| `data/spot-testnet-public-depth-v2-20260913-replay-1.json` | `00c30f21e82e4d783a1279a784a14a70c1fa66ba2c6fa8a9b2b680897586c4aa` |
| `data/spot-testnet-public-depth-v2-20260913-replay-2.json` | `00c30f21e82e4d783a1279a784a14a70c1fa66ba2c6fa8a9b2b680897586c4aa` |
| Completion row | `a81e9a3ee34434d89181f22508f092f269bac4ce69cf96aece4bbfd9635624db` |
| Canonical native quote list | `4cd2c2eecdeb75112dded503fbdce675538f609e4a0f22d60de360e58f64c8bd` |

The capture CLI's immediate detached replay matched its live diagnostic summary.
Two additional standalone CLI processes then selected the original hash with
`--revision 2` and produced the identical numeric native quote reports above.
Both returned exit 0, `historical_replay_only=true`, and all six qualification
flags false. Replay performs no exchange requests and creates no reusable live
fence, account state or execution checkpoint. Hash equality detects changes in
selected bytes; it is not independent venue authentication.

## Verification and next work

Before the attempt: **107 focused tests passed**, and full offline regression
reported **2,804 passed / 12 deselected in 218.11 seconds**. The excluded Postgres
integration cases lack a dedicated DSN. Ruff for apps/tests, research registry,
frozen contract hashes, original-v1 compatibility and document links passed.
After the attempt: two actual fresh-process replays, report byte equality,
artifact/quote/completion hashes, request counts and unchanged original-state
hashes were checked. Subsequent edits are documentation only.

The original v1 failure still has SHA256
`f2af2aba60ab0bbde04f37948b7f4d03b0222ec1cd07b36acadd18685eabbfed`;
it is not repaired, relabeled or counted as successful v2 evidence. The fixed
ADR-017 `native.json` still matches
`08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f`.
No upstream source, Key/permission, private session, risk/SourcePolicy, signal,
execution path, service or schedule changed. No BUY, SELL or cancel was sent.

Next design a bounded fixed-route coverage/budget experiment before account/market
fan-out: retain unpriced assets, finite-depth exclusions, shared-IP costs and
independent observation intervals. A fresh selected account/metadata route set is
required for a later actual experiment; historical routes do not become fresh
because BTCUSDT replay passed. Do not infer complete equity or simultaneous
account/market revisions from one symbol. Full-account/UTC/flow/reset qualification,
actual fills/cleanup and strict **0/14** remain blocked.
