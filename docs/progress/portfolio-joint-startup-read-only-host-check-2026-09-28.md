# Protected read-only joint startup check on the host

Date: 2026-09-28. Commit `96dc4b1` fixed the separate
`gateway_window_startup_check.py` source. `git show` of that commit and the
clean checkout agreed on SHA256
`36c9f10a3c4e11140029e709f8493b6d08cd3b0659faf7bdd6b22fbf1ccecbbc`.
Before staging, a read-only host check matched the previously selected base
manifest SHA256 `3f53ffb0bf93444a22a8aca569887338c8639c95c052c19713a1efcf06ed2882`,
the unchanged joint manifest SHA256
`6d3dbe6fa8edaa77fe0f8ff6c0e7d9268462449eaba836d73cd02afab9d4ea91`,
and the pinned installed base helper. The target path was absent.

One root-owned 0755 directory `/run/trader-egress-window-startup-v1` and one
root-owned, single-link 0444 file `startup-check.py` were staged there. The
staged file hash matches the reviewed commit. The isolated system-Python
process selected the existing base and all six installed joint sources,
executed their read-only fixed entry check and returned exit 2 with
`joint_window_protected_startup_observed_unqualified`. Repeating only this
read-only check with an invalid base-manifest hash returned exit 2 with
`joint_window_protected_startup_refused`. All admission fields remained false.
No existing installed source, manifest or base code was replaced; the old
first-install-only `apply` was not run.

The independent disposable mount/net/PID installation fixture accepts a
correct base selection and refuses a wrong hash, unprotected startup-file
mode, and a self-consistently reinventoried installed source. Its ignored
write-once report `data/joint-window-isolated-2026-09-28-r9.json` has SHA256
`2a1c74d9c21beae55c68a228295c7d9b5dc6f196bffa779f596f76833a7054a4`:
40 base and 24 joint checks pass, host observations match before and after,
and zero venue requests were made. The 106 related Python tests and code
checks passed. A post-stage host read still found neither `inet` nor `netdev`
joint nft table; the original installed entry continued to exit 2 unqualified.

This check attests only the one read-only process launched from the selected
root-owned path. The `/run` staging is ephemeral, not a reboot-startup unit
or an activation controller. The script has no nft or grant interface and
does not attest the separate fixture process that writes nft. Before any
future startup, the committed source hash and independent base selection
must be checked again; disappearance of `/run` does not authorize reinstalling
the original six sources. A protected controller lifecycle, complete caller
and source ownership, uninterrupted 425-second exclusion and fresh provider
bounds remain missing. No venue request or trading path was affected.
