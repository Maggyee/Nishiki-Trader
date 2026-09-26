# Isolated one-shot joint blackout transaction

Date: 2026-09-26. The staged controller now links the held selection and
one-shot witness to a real nft transaction in a disposable user/network
namespace. It checks both preinstalled tables' exact selected rule shape and
empty blackout/permit sets, fsyncs a `claimed` record, then fsyncs an
`activation_prepared` record before issuing exactly one `nft -f` with four
same-duration IPv4/IPv6 blackout elements across the inet and netdev tables.
It never writes to either `permits` set. An immediate held snapshot checks the
selected rules and active timers; a failed write or changed snapshot leaves
the scope consumed and the holder closed. It cannot retry or grant egress.

The real isolated nft test uses a five-second window and no network peer. It
confirms the installed timers, empty permit sets, one recorded observation and
false admission flags. An injected failed writer leaves only the prepared
intent and no active timers. Staged tests also reject a preexisting blackout, changed
rules even when the digest is recomputed, an invalid duration, and reactivation.
The witness now separates durable claim from first observation so a kernel
write can occur between them. The previous read-only witness report remains a
historical staging result, not continuous activation evidence.

The staged `RootSelectedWindowSnapshot` and controller are not installed or
pinned by a protected host entrypoint; the actual nft test uses a synthetic
selection around real kernel reads. There is no real-host joint table or
425-second interruption, permit population, venue request, authenticated
provider-visible source, all-caller route/mark proof, watchdog or continuous
history guarantee. Other privileged writers can change rules between checks;
crash after the nft transaction still leaves an uncertain, consumed scope until
timer expiry. The controller intentionally exports no `guard.verify()` and
does not authorize the first joint operation or trading.

Next exercise actual veth/NAT packet paths and independently protect the
installed selector/controller and one-shot storage before considering a
separately gated host interruption. Fresh provider intervals, unknown market
charge, full-account coverage and per-dispatch reservations remain blockers.

Verification: 71 related tests pass, including three real nft probes in
disposable user/network namespaces. Ruff, formatting and diff checks pass.
An intermittent held-file test also exposed a legitimate `atime` read race;
descriptor checks now compare stable identity fields and original bytes.
Neither power-loss durability nor any 425-second real-host window was tested.
