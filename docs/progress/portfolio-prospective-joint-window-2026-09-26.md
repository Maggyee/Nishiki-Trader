# Prospective joint first-operation window barrier

Date: 2026-09-26. `infra/egress-guard/gateway_joint_window.py` now joins a held
guard interface to the existing one-shot, fsynced joint attempt ledger for a
prospective **first-operation preparation**. It never grants kernel permission,
creates a venue socket, signs a request, or exports a rate/admission candidate.
It is not installed on the host.

The barrier requires a fresh joint ledger bound to the guard's selected identity,
an unchanged boot/manifest/binding and a fixed absolute exclusion expiry. The
selected window must cover at least the configured lookback plus the **125-second
capture/close horizon**. Lookback must be at least 300 seconds for connection
attempts and may be at most 3,600 seconds in this prototype. After the full
lookback elapses, it persists the fixed first `time` preparation, checking the
guard and ledger before and after the fsync. A premature attempt can wait; drift,
renewal, lost quarantine, short future coverage, unknown market charge, an
out-of-order operation or persistence failure permanently halt that scope and
attempt guard revocation. A pending attempt is never silently refunded.

The `guard.verify()` interface is deliberately an **unfulfilled trust boundary**:
an installed root controller must verify the actual kernel policy, every host,
container, proxy and IPv4/IPv6 route to the shared public source, the activation
journal and expiry before supplying it. A synthetic object can return the same
shape, so even a `local_window_mature` result is only a timing check. This module
does not prove uninterrupted kernel coverage between checks, establish the
public source as seen by Binance, authenticate pre-existing REST/WS rate samples,
derive every provider interval for lookback, or bound all other callers' charges.
The current 20-second disposable maintenance fixture cannot provide the required
minimum 425 seconds of exclusion. Such an extended real-host interruption has
not been installed or exercised.

The next implementation step is to build and independently test the root-owned
kernel/source observer and activation journal, bind its actual evidence to the
frozen REST/account/market destination and address-family policy, and derive
lookback from authenticated provider intervals. Then extend the fixed 21-step
gateway with per-dispatch remaining-budget reservations. Unknown market charge,
fresh provider usage, complete asset coverage, stream fence and baseline/risk
qualification remain separate blockers. The consumed bootstrap and trade scopes
remain closed. All source, shared-egress and network/trading admission flags stay
false.

Verification: 13 focused tests use the actual consumed ledger and independent
archive replay; they cover incomplete history, one persisted preparation,
renewal/drift, clock regression, horizon loss, unknown charge, out-of-order
calls, fsync failure, foreign process identity and no second initialization.
The broader four-module run passes 233/233 tests when Unix socket sends are
permitted. An earlier restricted-sandbox run (before the last two focused cases)
had 221 passes and ten existing fixture-proxy cases failing at `socket.sendall`
with `EPERM`; the final full run passed without that sandbox restriction. No
upstream code or live trading path changed.
