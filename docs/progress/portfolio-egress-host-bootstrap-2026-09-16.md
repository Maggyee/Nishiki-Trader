# Actual host installation and authorized REST bootstrap

Date: 2026-09-16. Preparation accepted; actual GET pending in this revision.
The [accepted v2 contract](portfolio-shared-egress-bootstrap-2026-09-16-v2.json)
preserves the old draft and pins exact source and private evidence hashes.

The operator selected the existing public IPv4 and supplied OCI console VNIC,
private/public IP and all three OCIDs. IMDS private address, VNIC, MAC and VLAN
match exactly. Full identifiers remain in ignored private evidence. This is
operator-provided OCI provenance, not an authenticated cloud API export or a
measurement of the public source by the venue. The operator explicitly accepted:
“接受这个窗口和单次 GET 的额度不确定性”. This authorizes one maximum 20-second
ordinary-egress interruption, collector permission at most 12 seconds and one
unsigned public exchangeInfo GET with documented weight 20 and unknown prior usage.
No second IPv4, retry, redirect, private call or trading action is authorized.

## Completed installation and storage acceptance

The corrected bundle SHA256
`995380e089df6c658a2ee7fa8224441d6173ed08b9656fc6447fad85d62800ec`
was installed through protected root staging. Dedicated account `trader-egress`
has UID/GID 997, locked password, no login shell and no additional groups.
`/usr/local/lib/trader-egress` is root0755 with root0444 Python sources;
`/etc/trader/egress-install.json` is root0600; `/var/lib/trader/egress` is root0700
on ext4 `/dev/sda1`. Installed manifest SHA256 is
`3f53ffb0bf93444a22a8aca569887338c8639c95c052c19713a1efcf06ed2882`.
The fixed installed check passes inactive. The ordinary-user host inspector's
caller-owner mismatch does not describe failure of the root installation verifier.

Actual root-staged `host_acceptance.py` verifies distinct-UID launch, kernel IPC
credentials, pidfd-bound process identity, exactly one control observation, repeat
refusal, cleanup and nine kernel-denied code/manifest/state accesses. A separate
fresh helper reads the same acceptance-only consumed record; repeat preparation
is refused. Record SHA256:
`397ef1b5bdcaf2d811e59dfaf1c3a7f38e02217e89d40d8918130fced85b2050`.
Do not delete `/var/lib/trader/egress/installation-acceptance-v1`.
This is process restart acceptance, not host reboot, power-loss or rollback proof.
Before/after installation structural network snapshots match; sing-box, Docker
and tailscaled remain active. No venue request was made by installation acceptance.

## Fixed transport and bounded maintenance

`infra/egress-guard/bootstrap_once.py` requires isolated root Python and a protected
root0600 plan at `/etc/trader/egress-bootstrap-v1.json`. It checks the exact installed
manifest/account, runner/parser/CA hashes, boot/MAC, actual route/private source and
plan age at most 300 seconds. Fresh DNS selects exactly one literal IPv4 before
activation; transport does no resolution or fallback. Reviewed code is installed
root0444 under `/usr/local/lib/trader-egress-bootstrap-v1`; mutable checkout code
is not used as the installed privileged entrypoint.

The root helper consumes `/var/lib/trader/egress/rest-bootstrap-v1` durably before
creating topology. Root owns the journal, original plan and response bytes. A
capability-free UID 997 child in a dedicated namespace gets one TCP/TLS attempt
and one fixed `GET /api/v3/exchangeInfo` to `testnet.binance.vision`. TLS verifies
hostname and the system trust store, whose bytes are pinned. A credential-bound
SEQPACKET channel persists raw chunks before acknowledgment/interpretation. Limits
are 10 seconds plus a 2-second close allowance, 64 KiB headers, 8 MiB body, 16 MiB
archive and a 4 KiB incident reserve. Failure leaves the scope consumed.

A single nft transaction installs 12-second permits and 20-second blackout elements
in independent inet and WAN netdev tables. OUTPUT/FORWARD blocks ordinary IPv4/IPv6;
physical egress also blocks raw AF_PACKET IP bypass. The actual host has an LLDP
packet socket; ARP and LLDP are unaffected. No tc filter, flowtable or WAN XDP path
was observed. The guard permits only the marked collector flow to the selected
address/443. Own narrow FORWARD rules allow traversal of Docker's existing default
drop chain. SNAT uses the existing selected private address and cloud public mapping.

Final cleanup revokes permits before restoring ordinary traffic, terminates/reaps
the child, removes only owned rule handles, namespace/veth and tables, and records
cleanup errors. Kernel expiry restores ordinary traffic even if the helper dies;
the collector remains denied. No ordinary service is stopped. Kernel expiry cannot
prove provider quota history or prevent a malicious privileged firewall rewrite.

## Verification and next action

**533 focused Python tests passed** across egress, host acceptance, local bootstrap,
TLS provenance, rate parsing, joint TLS/transport and offline bootstrap review.
Tests include original-byte/semantic corruption, duplicate operations, partial
captures, bounded failures, fsync/abrupt-exit consumption and reopen refusal.
The local TLS bootstrap also replays in fresh processes without venue requests.

Final exact-source disposable success and SIGKILL runs pass using real kernel
namespaces, fixed host installation copies, distinct UID, TLS and Docker-style
FORWARD default drop. Normal and raw-IP competitors are blocked/restored; SIGKILL
restores ordinary traffic through kernel expiry while the collector stays denied.
Normal cleanup removes owned topology/rules. Both refuse reexecution with original
journal unchanged. Their reports and runner SHA256 are pinned in the v2 contract.
An earlier report filename collision refused before testing; historical artifacts
were preserved and final success used a new filename. All test peers were local.

Next commit/push this preparation, install the pinned bootstrap sources, refresh
DNS and create the protected fresh plan, then execute exactly once. Independently
inspect scope state after any tool disconnect; never repeat execution. Export
original bytes read-only, verify structural network/service restoration and replay
in two fresh processes. Add actual outcome as a successor result document.

The frozen joint contract SHA256 remains
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`:
17 GETs / 468 weight. This bootstrap does not grant joint capture, pre-request
headroom, account/UTC baseline, restart or trading admission. Prior consumed
ADR-017 and public-depth scopes stay intact; strict continuity remains 0/14.
Upstream source and live order paths are unchanged.
