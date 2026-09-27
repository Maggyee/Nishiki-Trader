# Joint-window extension bundle staged

Date: 2026-09-27. `gateway_window_package.py` adds a fixed first-install-only
extension for the already installed base four-file authority. `build` produces
a deterministic uncompressed USTAR archive with exactly six joint-window
sources, the installer's own bytes, README and SHA256 inventory. The builder
and inspector independently pin the base helper, entry and source adapter
bytes. `inspect` checks the selected whole-archive SHA256, exact canonical
tar bytes, fixed inventory and bounded regular members without extraction.

The selected ignored local candidate is
`data/joint-window-review-2026-09-27-r3.tar`, SHA256
`b4fa63202378ba609f0927e5dd121b7d6bd1c7dd9ab77818895a372af056a3f9`.
Its `install.py` SHA256 is
`6bc0a7a4bbe6915a0c3d84dfb9b4dabeea0747915a08209a5781ee0b8b028d23`.
The installed operation requires isolated UID 0, a protected root-owned
installer with exact selected bytes and the existing held base verifier.
It preflights absent joint files and manifest, exclusively creates/fsyncs
all six 0444 sources, then publishes the root-owned 0600 manifest bound to
the held base manifest hash. The entry file is the first partial-install
marker; failures leave evidence and make retry fail before further writes.
There is no activation, rule mutation, permit or venue request interface.

In private mount/network/PID namespaces the real base install passes its 40
checks, then the reviewed extension passes seven checks: wrong bundle SHA256
and unprotected installer mode before mutation, first install, fresh process
`--check`, repeat-install refusal without manifest change, wrong manifest pin
and source mode drift. A re-inventoried archive with changed entry bytes is
rejected by the fixed source pin. Every check keeps admission false. The
ignored local report `data/joint-window-isolated-2026-09-27-r7.json` has
SHA256 `cf285829dd4c215b3bf8a7c01bafe5f3f32ce82375765822203ea75a5070fd94`.
Host account/path observations and caller namespaces match before and after.
The actual installed base helper independently returns
`installation_verified_inactive`, exit 2, with no network admission.

This package is an operator-review candidate, not a host installation or
independent runtime attestation. Root-owned startup protection and operator
selection of the archive must precede applying it on the host. The host
has no joint manifest, rules or protected entry. The extension alone cannot
prove continuous 425-second exclusion, source/mark ownership, complete caller
coverage, fresh provider bounds or real collection. No trading path changed.
