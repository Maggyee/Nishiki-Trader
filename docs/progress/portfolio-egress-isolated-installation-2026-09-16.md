# Actual disposable installation and distinct-UID acceptance

The dedicated-user branch now passes **actual kernel/process/filesystem acceptance**
in disposable Linux namespaces. This advances the earlier
[bundle implementation](portfolio-egress-bundle-2026-09-16.md), whose installation
and account tests were simulated. No production host installation occurred.
The [v3 review contract](portfolio-egress-installation-contract-2026-09-16-v3.json)
pins the corrected installer, bundle and final retained report. Installed manifest
schema remains v2 and its four source hashes are unchanged.

## A real installer defect was found and fixed

The earlier installer used `useradd -K CREATE_MAIL_SPOOL=no`. On the current system,
`-K` only accepts login.defs keys; CREATE_MAIL_SPOOL is a useradd defaults setting.
Actual invocation exits 3 with `unknown item 'CREATE_MAIL_SPOOL'`. The mocked
account tests did not detect this. The original bundle is therefore historical,
not the package to deploy. Neither its bytes nor its v2 review contract were edited.

`package.py` removes those two unsupported arguments and retains `--system`,
`--user-group`, `--home-dir /nonexistent`, `--no-create-home`, `--no-log-init` and
`--shell /usr/sbin/nologin`. Real system-user creation now succeeds, `passwd -S`
reports locked, and no mail spool/login log is created even when the fixture sets
`CREATE_MAIL_SPOOL=yes`. No global useradd defaults are changed.

Corrected artifact: `data/egress-installation-bundle-2026-09-16-v2.tar`

- Bundle SHA256: `995380e089df6c658a2ee7fa8224441d6173ed08b9656fc6447fad85d62800ec`
- Installer SHA256: `7f519e26c0f85951e8d60f8cf8eaa6e774fb002c74647ee4892b491cef8b549d`

The fixture rebuild and standalone build reproduce this same pin; standalone
inspection passes. Hash equality binds reviewed bytes, not a publisher identity.

## Disposable fixture and observed results

Read-only sudo inspection now reports existing noninteractive permission. That
allows `installation_selftest.py` to run `sudo -n unshare` with fresh private mount,
network and PID namespaces, without installing subordinate ID mappings or helpers.
The worker requires root/PID 1 and changed namespace identities before mounts.
Propagation is made private before covering `/etc`, `/run`, `/usr/local/lib`,
`/var/lib`, `/var/log`, `/var/mail` and `/tmp` with disposable tmpfs mounts.
Only synthetic root passwd/group/shadow records are written; original host secret
or account databases are not copied. No interface is brought up, route configured,
external socket opened or firewall rule installed.

The reviewed installer is staged root-owned 0444 in the isolated `/run` tree and
executed with isolated system Python at its exact bundle hash. Real useradd selects
fixture UID/GID **20999**, distinct from the helper's UID 0. This is an observed
fixture identity, not an assigned host ID or future provisioning instruction.
The following **40 checks pass**:

- Fresh namespaces, synthetic accounts, actual system-user/password-lock creation,
  first installation, no mail/login-log creation, and fresh fixed-entry verification.
- `FixtureCollector.from_installation` with actual distinct UID, per-message kernel
  credentials, pidfd, empty supplementary groups, all capabilities zero, and
  no-new-privileges. All four observed UID/GID fields equal 20999. The child has a
  further separate network namespace. One authenticated control observation passes;
  the second is refused and normal closure reaps the child/descriptors.
- A separate fixed same-UID probe reads each source but receives EACCES/EPERM for
  writes, unlink and chmod. It also cannot read/write/remove the manifest, list
  storage, read/write/delete the synthetic consumed record, create a new scope,
  or rename the root-owned code directory. These are actual kernel operations.
- Original consumed fixture bytes survive installation and a rejected second apply.
  Changed storage permissions block a fresh installed check and invalidate held
  authority permanently; restoration does not revive it. A new read-only check can
  observe restored state but still never grants admission.

The installed collector's finite protocol is unchanged. Filesystem attack probes
run as a separate bounded fixture process with the same UID/GID/groups/capability
policy; they are not new commands exposed through the collector/helper channel.
All code/state being attacked is disposable fixture state, not real consumed scopes.

Final retained report: `data/egress-isolated-installation-2026-09-16-final.json`

- Report SHA256: `23bbbbd5624bb4aaf9088d4cdbea02b4fa6858f43a8129e51bbb3fa4939c1a14`
- Harness SHA256: `199d195f9819efdb45a5660220763fce92e3f893f35f859842c0ec98c798812a`

The caller namespaces and selected host observations compare equal before/after:
passwd/group byte hashes are unchanged, and all three fixed host installation
paths remain missing. This does not assert an exhaustive host audit. The report
contains no shadow/password data. The worker has a 45-second alarm, individual
commands a 10-second timeout, parent communication a 55-second deadline, and PID
namespace teardown kills remaining descendants. All temporary account/filesystem
changes disappear with those namespaces.

Three diagnostic attempts stopped at the old useradd option; their exclusive local
report files are empty, not successful evidence. A diagnostic run passed after the
fix, then the final run removed diagnostic instrumentation and executed the actual
installer CLI. Only the final report above is the selected acceptance evidence.

## Verification and next boundary

**335 focused Python tests pass**, including 14 new tests refusing unsafe worker
contexts before mounts, root invocation of the public wrapper, reused/symlink
reports and installer pin drift before sudo. Existing installation/package/launcher,
identity, host inspection and guard tests remain green. Ruff/check/format, links,
contract/report hashes and frozen original bytes pass. Earlier unchanged 14-check
launcher and 151-check network harnesses were not rerun.

```bash
/usr/bin/python3 -I infra/egress-guard/installation_selftest.py --report data/NEW-ISOLATED-INSTALLATION.json
.venv/bin/pytest -q tests/ops/test_egress_installation_selftest.py tests/ops/test_egress_package.py tests/ops/test_egress_installation.py tests/ops/test_egress_collector_launcher.py tests/ops/test_egress_binding_inspection.py tests/ops/test_egress_host_inspection.py tests/ops/test_egress_guard_selftest.py
```

Actual host installation, persistent disk/restart/power-loss behavior, source
mapping and complete egress paths remain unqualified. Next review the corrected
bundle for inactive host installation and those checks, then implement the separate
bootstrap transport and fixed activation operation. Existing sudo availability is
not approval for host network interruption or collection.

The existing IPv4 and proxy are preserved. No host account, sudoers rule, service,
network policy or upstream source changed. The live trading path is unaffected;
strict continuity stays **0/14**, and consumed ADR-017/public-depth scopes plus the
17-GET / 468-weight joint contract remain intact. `docs/project-status.md` and the
reading index have been updated for this actual acceptance milestone.
