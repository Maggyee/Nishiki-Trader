# Original bootstrap evidence joined to the offline joint gate

Date: 2026-09-16. Integration complete; joint admission remains blocked.

`apps.ops.portfolio_joint_admission` now accepts the three original bootstrap
artifacts and their independently selected hashes. It replays the raw HTTP and
receipt chain, verifies plan/collector/TCP/TLS consistency, then joins historical
rates and timing to the existing frozen joint gate. The old candidate mode remains
unchanged. No new network request, root execution, firewall mutation, credential
read or scope activation is performed by this mode.

## Actual finding

The original full response header was persisted at **09:34:12.451486632 UTC**.
The complete response followed **7.822518713 seconds later**, already beyond the
joint contract's **5-second** sample age limit. A completed-body timestamp cannot
refresh that earlier counter. This does not invalidate the successful single GET;
it prevents its result being reused as a fresh dispatch permit. Header persistence
is a local receipt bound, not proof of the provider's exact counter sampling time.

The original body reports `serverTime=1789551252318`. It is retained as a reported
value; neither that value nor HTTP `Date` supplies a qualified server-clock offset
interval by itself. The actual historical review has matching boot identity and
consistent UTC/monotonic receipts. Other-boot, clock-drift or pre-cleanup review
instants leave age unknown and add a blocker rather than inventing freshness.

| Evidence | Incorporated result | Remaining condition |
|---|---|---|
| Original REST response | HTTP 200, 2,495,288 body bytes; original hash/framing/TLS receipts match | Fresh qualified pre-dispatch sample and server-clock interval |
| REQUEST_WEIGHT | Limit 6,000/minute, response counter 20 | Current usage upper bound and competing-caller bound remain unknown |
| RAW_REQUESTS | Limit 300,000/5 minutes | Usage remains unknown; the single local GET is not a global count |
| ORDERS | Limits 50/10 seconds and 160,000/day | Account scope is preserved; public IP evidence does not qualify it |
| Host maintenance | Historical 8.38-second activation-to-cleanup interval | No coverage before activation, after cleanup or for the next dispatch |
| Source records | Selected UID, peer, TLS, source commit and manifest references match | Root/source/gateway authority qualification is not conferred by a matching hash |
| Account/market WS | No bootstrap observation | Fresh account samples, complete rolling connection history and market connection charge remain missing |

The 20-second one-shot approval is consumed. It cannot cover the joint contract's
complete **300-second rolling connection history** and **125-second capture/close
horizon**. Waiting after cleanup supplies no all-caller history. There is no new
maintenance authorization in this report.

The maximum remains **17 GETs / 468 documented weight**. The earlier bootstrap is
a separate consumed scope, so its GET/weight are not subtracted. Calculated headroom,
other-caller bounds and unobserved usage stay null. All source/egress, reservation,
network and trading admission flags remain false. Bootstrap consumption is true;
joint-scope consumption is false. No fabricated candidate or retroactive signature
is created to fill the missing evidence.

## Reproduction

```bash
.venv/bin/python -m apps.ops.portfolio_joint_admission \
  --bootstrap-plan SELECTED-PLAN.json --bootstrap-plan-sha256 ORIGINAL-PLAN-SHA256 \
  --bootstrap-events SELECTED-EVENTS.jsonl --bootstrap-events-sha256 ORIGINAL-EVENTS-SHA256 \
  --bootstrap-response SELECTED-RESPONSE.bin --bootstrap-response-sha256 ORIGINAL-RESPONSE-SHA256 \
  --report data/NEW-BOOTSTRAP-JOINT-REVIEW.json
```

Inputs use the existing bounded private-file reader. All three files/hashes must
be selected together; they cannot be mixed with a self-reported candidate. Current
review times use the local boot ID. Historical replay requires paired `--at-ns`
and `--monotonic-ns` plus explicit `--boot-id`. Report creation remains exclusive,
0600 and fsynced. Exit 2 means a blocked report was written; exit 1 means validation
or publication failed. Review is repeatable only into new report paths and never
reopens the original capture scope.

The actual original pins were rechecked against the prior immutable result.
Two fresh processes produced identical reports, SHA256:
`95a8d22949bf3ba0b2c4d87be90324ac382cea01f34721b74181df2b1b4e4ffc`.
The [machine-readable result](portfolio-bootstrap-joint-review-2026-09-16.json)
pins both reports, the selected historical review times and original input hashes.

## Implementation order from these gaps

1. Qualify actual source/gateway authority against deployed root-owned code,
   account, route and storage records; retain the distinction between signer
   authorship and coverage authority.
2. Prepare prospective all-caller accounting and dispatch enforcement. Acceptance
   must include failed/uncertain attempts, full applicable history, source drift,
   rolling connections, future competing usage and crash/expiry behavior. A longer
   or new host interruption needs its own concrete reviewed scope; do not extend
   the consumed bootstrap approval.
3. Prepare fresh rate/clock acquisition and consumption within that control scope.
   Bind counter receipt time to dispatch rather than completed-body or replay time.
   Any smaller-response selector or policy change belongs in a new contract, not
   an edit to the frozen draft or a rerun of the old scope.
4. Resolve the provider's market-connection charge and account/IP applicability.
   Missing definitions or evidence remain blockers; no assumed-zero charge.
5. Join qualified evidence to remaining-budget reservations, durable one-shot
   activation and the real joint transport. Exercise failures and two fresh replay
   processes before reviewing a concrete network run.

These are implementation dependencies, not deployment or trading authorization.
Code entrypoints and acceptance requirements are listed in the JSON result.

Verification: **20 new / 234 focused tests pass**, covering slow-body/header age,
split headers, exact age boundary, clocks/boot, rehashed identity changes,
incomplete captures, unknown counts, unchanged full budget, private/exclusive
CLI output, changed original bytes, no DNS/socket I/O and independent processes.
Ruff, formatting, evidence/frozen hashes, local links and diff checks pass. Kernel
harnesses and full application regression were not rerun because privileged
transport and its installed sources are unchanged. Historical reports and consumed
scopes are preserved. No upstream source or live order path changed; strict
continuity remains 0/14. Project status and reading index now point here.
