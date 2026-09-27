# Read-only host namespace and Docker route inventory

Observed: 2026-09-27. `host_namespace_inventory.py` ran as an ordinary user
and used fixed noninteractive sudo commands for `lsns`, Docker container IDs
and PIDs, `/proc/<pid>/ns/net` readlinks, and IPv4/IPv6 `ip -j route` under
each representative network namespace. It reread each PID's namespace and
the namespace/Docker lists to detect changes during the census. Docker CLI
used its local daemon socket; no external venue request was made and no host
route, rule or process was changed. The
write-once private report is ignored under
`data/host-namespace-inventory-2026-09-27-r2.json`, SHA256
`b2bdc1128fbc8bc1952da03fcef453d90a5604b69a1f6200f8ceef3517b98279`.
The report contains namespace/PID/route and container identifiers; do not
publish it as public infrastructure metadata.

The 101 recorded reads had no errors or census drift. Twenty namespaces were
visible. Seventeen had an IPv4 default route: the host and 16 distinct Docker
namespaces mapped to all 16 running containers. The only IPv6 default route
observed was in the host namespace. The remaining three visible namespaces
had no default route at this instant. No other currently routed non-host
namespace appeared outside the Docker mapping. The earlier manual snapshot's
counts agree, but this report now binds each Docker PID to the `lsns` namespace
and reads both families' routes within it. Every admission field remains false.
When a route family or Docker mapping is incomplete, its count is `null`, not
zero; unit tests cover that failure path and namespace representative changes.

This is an inventory, not a caller-exclusion proof. Containers and PIDs may
appear or disappear immediately after the read; a proxy can forward across
namespaces, and route tables do not reveal every effective policy rule, mark,
NAT outcome or provider-visible source. Current coverage must be bound to a
protected continuous lifecycle and packet-path authority before a host
blackout could be considered. The joint host rules/controller are absent.
No activation, permit, venue request or trading operation was performed.
