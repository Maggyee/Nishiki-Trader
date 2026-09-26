# Joint kernel observer held-selection prototype

Date: 2026-09-26. `gateway_window_custody.py` removes a caller-selected rule
digest from the intended installed observation path. It requires an isolated
root process and uses the existing `TrustedInstallation.open_file` contract to
hold a fixed root-owned 0600 plan and fixed 0444 observer source. The plan ties
the two rule digests, WAN name, observer SHA256 and base installation manifest
to the current boot, network namespace and user namespace. The adapter checks
held bytes and identity both before and after the nft observation; any detected
drift closes the held authority. It has no writer, grant, activation, transport
or `guard.verify()` interface. Reports always deny authenticated source,
all-caller coverage, activation history and network admission.

Staged tests exercise real observer source bytes with a test-only descriptor
holder and synthetic nft output. They verify bad plan fields, changed source,
file/namespace drift and forged admission results fail closed. This is a unit
test of the adapter's use of the existing installation API, not an acceptance
of an actual root-owned installation. The adapter's own code is not installed
or pinned by a protected entrypoint. A read-only privileged host nft ruleset
check found **zero** `trader_joint_window_v1` rows; no host guard was activated.

Next bind this adapter to independently reviewed, protected installed code and
an immutable one-shot activation journal, with actual host/container/proxy route
and provider-visible source proof. A stored return timestamp or a current
timeout snapshot alone cannot prove uninterrupted exclusion for the 300-second
history plus 125-second horizon. Fresh provider intervals and usage bounds,
unknown market charge and full-account coverage remain separate blockers.
No venue request, host network mutation, consumed-scope reopening or live-path
change occurred.

Verification: 11 staged selection tests, the adjacent kernel observer tests
and the first-operation barrier tests pass; lint and format checks pass.
