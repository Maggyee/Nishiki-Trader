# Read-only joint kernel window observation prototype

Date: 2026-09-26. `infra/egress-guard/gateway_window_kernel.py` checks two
caller-pinned nft tables and their actual timeout elements, with a conservative
read-time-adjusted monotonic expiry. It fails on changed rules, missing IPv4/IPv6
memberships, populated permit sets or a mismatched netdev device. Its output is
always `local_kernel_timers_observed_unqualified` with false source, complete
caller-coverage and network-admission fields. It cannot provide a `guard.verify()`
assertion to the prospective first-operation barrier.

An ephemeral `unshare -Urn` test created the two tables and 5-second timer
elements, then read them through the real nft binary. This host's nft 1.0.2
returns remaining timers as integer seconds, `ip`/`ip6` for netdev EtherTypes,
and omits the netdev hook device from JSON even in `list chain`. The observer
therefore also reads fixed text output for that chain and rejects a missing or
different device. The additional read does not prove that the tables were
unchanged between commands or continuously since activation.

The expected static hashes and WAN name are still supplied by a caller, with
no root-owned pinned policy, activation journal, independently established
namespace/route identity or uninterrupted all-caller exclusion. Nothing here
authenticates the provider-visible source or reserves other callers' usage;
fresh provider intervals and unknown charges also remain unresolved. The
20-second historical bootstrap interruption cannot meet the proposed 425-second
joint history/horizon. No host nft rules, venue requests, installed code or
live trading path changed. Next establish protected installation and activation
custody plus complete route/source coverage, then bind authenticated provider
intervals and per-dispatch reservations before considering a distinct gated
testnet collection. Consumed scopes remain closed.

Verification: 12 focused tests pass, including one real nft run in a disposable
user/network namespace; the adjacent first-operation tests pass separately.
