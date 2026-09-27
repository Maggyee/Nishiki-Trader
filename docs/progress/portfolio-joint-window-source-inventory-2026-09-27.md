# Joint-window fixed source inventory staged

Date: 2026-09-27. `gateway_window_sources.py` adds a read-only fixed inventory
for the future joint-window root controller. A held base `TrustedInstallation`
must open a fixed root-owned 0600 manifest at
`/etc/trader/joint-window-sources-v1.json` and five fixed 0444 sources under
`/usr/local/lib/trader-egress`. The manifest binds its exact file inventory
and SHA256 values to the installed base manifest SHA256. The inventory includes
its own source, kernel observer, selection adapter, one-shot witness and
blackout activation module. It checks all source bytes before exposing any,
then rechecks the manifest, every source and isolated root identity on each
`source()` access. Missing/extra fields, duplicate keys, wrong pins, changed held bytes,
changed mode and loss of root identity fail closed and close the authority.
No source is executed or installed by the inventory.

The tests use a staged descriptor holder and local copies of the actual source
bytes. Thirteen inventory tests pass, including negative cases; the six related
window modules pass **73 tests** together, including the earlier real isolated
packet-path and nft activation probes. Ruff, formatting and diff checks pass.
Test custody does not establish an installed root verifier, protected manifest
or independent pin for the new adapter's own running code.

The existing base four-file installation and v27 fixture manifest are unchanged.
A separately reviewed first-install-only root entry and actual held manifest
are still needed before this adapter can anchor a host controller. Even that
installation would not establish uninterrupted host exclusion, mark ownership,
provider-visible source identity, complete host/container/proxy coverage or
fresh provider usage. No host rules, venue request, network permission or live
trading path changed.
