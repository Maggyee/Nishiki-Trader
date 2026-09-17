# Fixed installation, dedicated UID and gateway lifecycle integration

Date: 2026-09-17. Actual disposable namespaces and local echo peers only.

The [durable gateway lifecycle](portfolio-egress-gateway-lifecycle-2026-09-17.md)
now runs from fixed root-owned installed sources with the existing dedicated-user
launcher and a fixed protected storage root. `installed_gateway.py` is an isolated
fixture controller; `installed_gateway_selftest.py` joins the existing pinned
installation acceptance to this controller in five separate disposable environments.
No host package, account, rule, service, credential or consumed scope is changed.

## Installed custody and fixed scope

Each fresh private mount/network/PID namespace first runs the existing reviewed
installer and its 40 installation/UID checks. The original base bundle pin remains
`995380e089df6c658a2ee7fa8224441d6173ed08b9656fc6447fad85d62800ec`.
Actual `useradd` creates fixture UID/GID **20999**, distinct from root. This is not
the real host's collector identity or a new host provisioning instruction.

The fixture stages six additional root-owned 0444 sources under the existing
`/usr/local/lib/trader-egress`: the installed controller, ledger gateway, namespace
helpers, attempt ledger and its two stdlib dependencies. A separate root-owned
0600 `/etc/trader/egress-gateway-fixture.json` selects exactly these six hashes and
the original base installation manifest hash. The existing host installer/bundle
has no new apply mode; extension staging exists only inside this acceptance harness.

The fixed installed controller bootstraps the independently pinned base helper
entry through no-follow directory/file descriptors. It extends the existing
`TrustedInstallation` with the additional manifest/source descriptors before
loading their code. Every later installation/collector check therefore also checks
the original extension bytes, paths, modes, ownership and account policy. Observed
changes close that held authority permanently. No repository or site import search
path is enabled; the controller runs with isolated system Python.

Execution requires the exact installed entry path, `--fixture`, root, a PID-1
parent, and a protected `/run/trader-egress-gateway-fixture.json` selecting fresh
mount/network/PID namespaces. The parent releases one fixed stdin barrier after
activation; it cannot supply an endpoint, payload, source, UID, scope or renewal.
These checks constrain the fixture entrypoint, not a malicious root administrator.
The controller opens the attempt ledger only under `/var/lib/trader/egress`, with
its existing fixed `local-egress-attempts-v1` consumed directory. There is no
caller-selected storage root. Existing synthetic consumed bytes remain intact.

`FixtureCollector.from_installation` authenticates the separately launched UID
using kernel message credentials and pidfd. It has no capabilities, supplementary
groups or privileged inherited file descriptors, and has its own unconnected
network namespace. The root gateway retains the fixed marked echo socket. The
binding joins installed manifest identities, the actual child, selected route,
namespace and structural deny rules. Dynamic timeout elements remain excluded
from the structural hash; the kernel enforces their lifetime. This remains sampled
local binding, not continuous all-caller source qualification.

## Actual integration results

All five independently installed scenarios pass. Each runs 39 integration assertions
(40 for the crash case), in addition to the reused base installation's 40 checks.

| Scenario | Fixed echo sent | Attempt archive | Last lifecycle record |
|---|---:|---|---|
| Success | 1 | Closed; succeeded | `revoked` |
| Installed code changes after activation | 0 | Gap; pending/uncertain | `revoked` |
| Dedicated account gains another group | 0 | Gap; pending/uncertain | `revoked` |
| Protected storage mode changes | 0 | Incomplete; pending/uncertain | `activated` |
| Controller SIGKILL after activation | 0 | Incomplete; pending/uncertain | `activated` |

A separate probe using the exact dedicated UID/GID/capability policy performs real
kernel operations. It cannot write, unlink or chmod any of the six sources; read,
write or delete the selected manifests/context/journals; create an alternative
scope; or manufacture SO_MARK. Unmarked TCP is denied while permission is active,
with an increase in the intended OUTPUT deny counter. No descriptors for protected
code, manifest or state files appear in the authenticated collector's descriptor set.

Code/account drift is observed after the durable grant acknowledgement and before
send, blocks sending, and still permits recording verified revocation. Storage
mode drift blocks journal persistence; kernel revocation is attempted and verified
but cannot be written as a durable result. SIGKILL leaves a permit present until
its five-second kernel timeout. The parent does not flush it to manufacture expiry.
A trusted marked diagnostic socket is then denied in every scenario, with counter
confirmation. Missing revocation records stay unknown in historical replay.

After each terminal scenario, the fixture restores only its injected drift and
launches a new process from the fixed installed entry. The original scope is
refused with `FileExistsError`; both exact journals and prior consumed bytes remain
unchanged. Restoration does not reopen a scope or revive the old held authority.
All processes and private mounts disappear with namespace teardown.

## Verification and evidence

**34 new / 473 focused Python tests pass.** New cases cover selected extension
inventory/base pin/source hashes, no-follow file protections, fixed isolated entry
and namespace context, permanent invalidation, and refusal before sudo for root,
reused/symlink output or installer pin drift. Existing installation, package,
launcher, gateway, attempt ledger, guard, authority and TLS persistence tests pass.

The first actual five-scenario run passed and is retained without source changes.
Two fresh isolated system-Python processes revalidate the selected installed source
inventory, manifest/binding linkage and both journal types for all five scenarios.
Their reports are byte-identical and match the original worker reports. Archives,
source copies and replay driver live under `data/egress-installed-gateway-2026-09-17/`;
exact pins and outcomes are in the [result JSON](portfolio-egress-installed-gateway-2026-09-17.json).

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --report data/NEW-INSTALLED-GATEWAY.json
/usr/bin/python3 -I data/egress-installed-gateway-2026-09-17/replay.py
```

The wrapper uses existing noninteractive sudo only for fresh private namespaces.
The reused installation stage has its original 45-second alarm; the integration
stage resets it to 60 seconds, with a 70-second parent deadline per scenario and
process-group cleanup. Selected host account hashes/path metadata and caller
namespaces compare equal after every scenario. This is not an exhaustive host audit.
Ruff/format, retained pins, local links and diff checks pass. The full application
suite and unchanged standalone older kernel harnesses were not rerun.

## Remaining work

The installed integration still sends one fixed local echo, not HTTP/TLS or a real
provider request. Next bind the existing bounded local TLS collection to gateway
request classification and per-dispatch accounting, retaining original header
receipt times and unknown connection charges. Do this in isolation before proposing
any real rollout. Actual all-caller/source policy, complete history, future competing
usage, provider charge applicability and fresh rate/clock bounds remain required.
Privileged rule replacement races, persistent host installation, power loss, reboot
and storage rollback are not qualified by these tmpfs tests.

The consumed actual bootstrap remains consumed; the frozen joint contract is still
17 GETs / 468 documented weight, strict continuity 0/14, network/trading blocked.
No upstream source or live order path changed. Project status, reading index and
infrastructure README are updated; detailed evidence is archived here.
