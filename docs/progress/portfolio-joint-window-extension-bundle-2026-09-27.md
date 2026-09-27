# Joint-window extension bundle staged

Date: 2026-09-27. `gateway_window_package.py` adds a fixed first-install-only
extension for the already installed base four-file authority. `build` produces
a deterministic uncompressed USTAR archive with exactly six joint-window
sources, the installer's own bytes, README and SHA256 inventory. The builder
and inspector independently pin the base helper, entry and source adapter
bytes. `inspect` checks the selected whole-archive SHA256, exact canonical
tar bytes, fixed inventory and bounded regular members without extraction.

The selected ignored local candidate is
`data/joint-window-review-2026-09-27-r5.tar`, SHA256
`2858888679298b9fec3321739e1eb2755c211b9d0b88226d899da283a1c7c5bf`.
Its `install.py` SHA256 is
`99a322383d32e6248fb0ecf930243a111b4f07483ca18670a108eeaa6fe9f52c`.
The installed operation requires isolated UID 0, a protected root-owned
installer with exact selected bytes, the existing held base verifier and an
independently selected `--base-sha256` of the existing base manifest. It checks
the lowercase 64-hex pin against the held verifier before opening target
directories or writing anything. It preflights absent joint files and manifest,
exclusively creates/fsyncs all six 0444 sources, then publishes the root-owned
0600 manifest bound to the held base manifest hash. The entry file is the first partial-install
marker; failures leave evidence and make retry fail before further writes.
There is no activation, rule mutation, permit or venue request interface.
The protected installer also accepts read-only `audit` with the same selected
archive and base manifest SHA256. It loads the selected inventory adapter from
the reviewed archive through the held base verifier and compares every installed
joint source byte with the selected archive. The audit neither writes files nor
attests the identity of a future process started through the installed entry.

In private mount/network/PID namespaces the real base install passes its 40
checks, then the reviewed extension passes 13 checks: wrong bundle and base
selection, unprotected installer, absent-install audit, first install, selected
source audit, fresh process `--check`, repeat-install refusal, self-consistent
source/manifest drift and independent audit refusal, and manifest pin and source
mode drift refused by both checks. A re-inventoried archive with changed entry
bytes is rejected by the fixed source pin. Every check keeps admission false.
The ignored local report `data/joint-window-isolated-2026-09-27-r10.json` has
SHA256 `a517ecdc0cb5f3d834393d487a82675a1b3676aed94578a132e5e775020403b6`.
The fixture base manifest SHA256 is
`618251af135ac3f49764301f73c6ed1d176a64fbd9cbe1f3e7dc984b3091ed53`;
it is not a host pin. A read-only host check on September 27 observed
`/etc/trader/egress-install.json` SHA256
`3f53ffb0bf93444a22a8aca569887338c8639c95c052c19713a1efcf06ed2882`.
An operator must independently select the expected host hash and refuse any
drift at installation; this observation alone grants no installation approval.
Host account/path observations and caller namespaces match before and after.
The actual installed base helper independently returns
`installation_verified_inactive`, exit 2, with no network admission.

This package is an operator-review candidate, not a host installation or
independent runtime attestation. Root-owned startup protection and operator
selection of the archive and base manifest must precede applying it on the
host. The host has no joint manifest, rules or protected entry. The extension
alone cannot prove continuous 425-second exclusion, source/mark ownership, complete caller
coverage, fresh provider bounds or real collection. No trading path changed.
