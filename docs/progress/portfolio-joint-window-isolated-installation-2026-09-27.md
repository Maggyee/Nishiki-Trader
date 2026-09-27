# Joint-window isolated installed check

Date: 2026-09-27. The new `gateway_window_installation_selftest.py` runs the
existing pinned base bundle/installer in fresh private mount, network and PID
namespaces, then stages all six fixed joint-window sources as root-owned 0444
files with a root-owned 0600 manifest bound to that base installation.
The fresh `/usr/bin/python3 -I` fixed-path `--check` exits 2 and reports
`fixed_joint_window_sources_observed_unqualified`, with every admission flag
false. A wrong source digest in the joint manifest and a changed source mode
each exit 2 with `joint_window_sources_missing_or_changed` and all flags false.

The existing base fixture's 40 checks pass before the three joint checks.
The accepted ignored local report is
`data/joint-window-isolated-2026-09-27-r2.json`, SHA256
`cd3b78c551ffb6dbf1976e84d714c5afb383a5bbca343761fb5abed442dcb8e0`.
The wrapper compares host account hashes, fixed-path metadata and caller
namespaces before/after; no host joint entry or manifest was installed.
No interface was brought up, venue request made or network admission granted.

The harness copies checkout candidates into its disposable root filesystem;
it does not implement a reviewed first-install-only host extension or establish
an independent protected pin for the running entry. A protected startup anchor,
manifest publication and host source/caller coverage still need separate
review and evidence. No continuous 425-second host exclusion was run and no
live trading path changed.
