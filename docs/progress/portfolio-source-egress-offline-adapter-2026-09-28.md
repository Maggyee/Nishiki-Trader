# Offline source and shared-egress consistency adapter

Date: 2026-09-28. `infra/egress-guard/gateway_source_egress.py` is an offline
entrypoint over the existing held base/gateway source interfaces, a guard
observation and the consumed joint attempt ledger. It has no CLI, nft writer,
socket, credential, dispatch or admission API. It is not in the protected
installed six-source inventory, and no host controller invokes it.

The adapter rechecks held manifest digests and `gateway_joint_ipc.py` bytes,
requires a dedicated collector UID, and compares all three fixed REST/account
WS/market WS endpoint bindings against supplied route/source observations. It
rejects missing roles, UID, address-family, namespace, destination or source
drift, and disagreement on the shared public source. It replays the original
joint attempt journal with its selected hash, counts failed/uncertain attempts,
and refuses an open, crashed, gapped or unknown-charge archive. A guard
observation must match the base manifest and ledger binding, cover at least
300 seconds before review and retain 125 seconds of future exclusion. A second
source/guard check rejects observed drift. Refusal permanently closes the
adapter object; a failed scope cannot be reused through it.

Even a clean fixture returns `offline_local_consistency_only`, with
`source_authenticated`, `complete_caller_coverage_verified`,
`provider_usage_qualified`, `network_admitted` and `trading_admitted` all false.
The supplied route/source records and guard interface can be forged by a
caller; fixed endpoint names and locally selected code do not prove the
collector's actual network UID, marked route/SNAT, provider-visible public IP,
other host/container/proxy callers, or uninterrupted enforcement. An ordinary
joint ledger does not record all such callers, and its prepared-attempt count
is not a provider usage bound. An archive after an owner crash does not prove
that kernel exclusion survives the crash. No provider request or host policy
change was made.

Next: independently pin a host controller and its selected source/UID,
destination and dual-stack route/mark/NAT policy; bind continuously enforced
host/container/proxy coverage and actual outbound attempts through shutdown,
including owner exit and lease expiry, to provider-visible source evidence.
Only then can fresh REST, account WS and market usage/charge intervals feed the
separate offline capacity and reservation reviewers. Unknown market connection
cost, account-wide coverage, testnet continuity and Phase 6 review remain
blocked.

Verification: 20 new cases and 111 related tests pass (131 total), including
real consumed joint-ledger replay, route/source drift, missing roles, failed and
uncertain attempts, crash truncation, unknown charge, guard gap, short lookback
and lease expiry. Ruff and formatting checks pass. No upstream source or live
trading path changed.
