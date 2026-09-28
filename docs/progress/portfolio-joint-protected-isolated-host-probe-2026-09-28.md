# Protected private joint probe invoked on the host

Date: 2026-09-28. After commit `1ec7f17` was pushed, the committed
`gateway_window_isolated_probe.py` and checkout both hashed to
`ea82995600baebb66dab834ca5487c925bbac3d5e45b0aee77d702d11e322026`.
Read-only host checks confirmed the previously selected base manifest
`3f53ffb0bf93444a22a8aca569887338c8639c95c052c19713a1efcf06ed2882`,
joint manifest `6d3dbe6fa8edaa77fe0f8ff6c0e7d9268462449eaba836d73cd02afab9d4ea91`
and protected startup script
`36c9f10a3c4e11140029e709f8493b6d08cd3b0659faf7bdd6b22fbf1ccecbbc`.
The protected read-only startup selected the installed six sources and exited
2 unqualified. The new probe path was absent; the host nft table list had no
`trader_joint_window_v1` table.

A root-owned 0755 directory `/run/trader-egress-window-probe-v1` and a
root-owned, single-link 0444 `probe.py` were staged. The staged probe matched
the reviewed commit hash. From that fixed path, isolated system Python ran
only `--probe` with the selected base and joint manifest hashes. The outer
process selected the installed sources and spawned a fresh mount/net/PID
namespace for the nft transaction; the nested PID 1 required an empty
loopback-only network and used private tmpfs for the plan and witness. The
invocation exited 2 with
`joint_protected_isolated_activation_unqualified`, one observation, false
`network_admitted`, selection hash
`6af2bb06017d6582cb5625911c6b126a483dfc7167defbd6cb97cdbd98f64207`
and private archive hash
`3845575edd15654f5cdff6b84e9c39d1b6f78557cf8825b08ab251e3d8777299`.
The archive lived inside the private temporary namespace and is not a durable
host activation journal. A second invocation with an all-zero base hash
exited 2 with `joint_protected_isolated_probe_refused` and false admission.

Post-run read-only hashes of both installed manifests and both protected
`/run` scripts were unchanged. The host nft table list before staging, after
staging and after the probe showed no joint table; no host nft writer, service,
collector, venue request, credential change or trading operation was invoked.
These point-in-time reads cannot prove the absence of every transient change,
and the probe's `host_firewall_modified=false` is its own assertion, not an
independent continuous firewall trace.

The protected `/run` probe is ephemeral and has no startup service or restart
policy. It attests this invocation's selected sources and a five-second
blackout only inside its own disposable network namespace. It cannot establish
host/container/proxy coverage, mark/source ownership, a provider-visible
source, uninterrupted 425-second exclusion, fresh provider bounds or network
admission. The installed six sources and first-install-only package were not
reinstalled. Further work requires separately designed host lifecycle and
all-caller/source evidence before any gated collection decision.
