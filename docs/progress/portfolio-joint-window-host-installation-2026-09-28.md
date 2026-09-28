# Joint-window read-only host installation

Date: 2026-09-28. The operator delegated the hash selection and read-only
installation. The selected candidate came from the previously committed
`089785c` review: `data/joint-window-review-2026-09-27-r6.tar`, SHA256
`5d453bfaff0933e920253212b6123c6d7da6ff23f7022d091290b1694a717f32`.
The expected base manifest SHA256 came from the earlier committed host review:
`3f53ffb0bf93444a22a8aca569887338c8639c95c052c19713a1efcf06ed2882`.
This delegated selection is recorded as such; it is not independent human
attestation of the archive or provider-visible source.

Before mutation, `git archive 089785c infra/egress-guard` was rebuilt in a
separate temporary directory and the resulting tar matched the selected local
archive byte for byte. The package `inspect` accepted its pinned bytes; 45
relevant unit tests passed. Fresh reads matched both selected hashes and the
base helper pin `2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b`.
The base fixed-path check exited 2 with `installation_verified_inactive`.
All six joint source paths and the joint manifest were absent, including
dangling-symlink checks. Protected root ancestors had expected ownership and
modes.

The exact selected installer SHA256
`4ee75b36a3c902b571727a6383944861f13903ff251dbfb3442fcb6277614ce3`
was staged at
`/run/trader-egress-window-089785c-20260928-r1/window-install.py` as a
root-owned, single-link 0444 file beneath a new root-owned 0755 directory.
The staged file hash matched the archive member. One `apply` with both selected
SHA256 values returned `joint_window_installed_inactive` with activation,
deployment qualification and network admission false. It wrote six root-owned
0444 files under `/usr/local/lib/trader-egress/` and one root-owned 0600
`/etc/trader/joint-window-sources-v1.json`, SHA256
`6d3dbe6fa8edaa77fe0f8ff6c0e7d9268462449eaba836d73cd02afab9d4ea91`.
The manifest binds the selected base hash and all six archive source hashes.
The original base manifest and helper hashes remained unchanged.

Fresh isolated-root processes returned:

- Protected `audit`: exit 0, `joint_window_installed_sources_observed_inactive`.
- Protected `check-entry`: exit 2, `joint_window_selected_entry_executed_unqualified`.
- Installed direct `gateway_window_entry.py --check`: exit 2,
  `fixed_joint_window_sources_observed_unqualified`.
- Existing `helper_entry.py --check`: exit 2, `installation_verified_inactive`.

Every admission/qualification field in these reports was false. A post-install
`nft -j list tables` contained no `trader_joint_window_v1` table; no host nft
operation, collector, network request, new trading operation or credential
change was part of this installation. The protected installer in `/run` is
ephemeral; if it disappears after reboot, its absence does not authorize a
reinstall, and the first-install-only `apply` will refuse existing files.

This installation establishes a fixed read-only source inventory at the host,
not an independently attested startup path. It does not establish continuous
425-second host exclusion, Docker/Tailscale mark and NAT custody, complete
host/container/proxy caller coverage, authenticated provider-visible source,
fresh provider bounds, or admission to real collection or trading. The next
entrypoint is a separate host activation and all-caller/source design review;
do not start a blackout or issue venue requests from this result alone.
