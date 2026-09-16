# Local root custody and source-route binding

Date: 2026-09-16. Implemented and verified on the actual host without venue I/O.

`infra/egress-guard/authority_binding.py` now binds the installed authority,
original consumed bootstrap files, deployed runner/parser/CA, dedicated account,
host boot/namespaces and current network structure into one held-descriptor check.
Previously these had independent hashes and observations; there was no single
object which invalidated that combined binding when an artifact or route changed.
This completes the local custody part of the next-step authority work from the
[bootstrap/joint review](portfolio-bootstrap-joint-review-2026-09-16.md).

## Implemented boundary

The root-staged CLI requires isolated root Python, three independently selected
original hashes and fixed filesystem paths. It loads only the pinned installed
`helper_entry.py`, whose loader establishes root custody of its verifier, then
uses the existing `TrustedInstallation`. No caller-selected code, path, key,
credential, command or output path is accepted by the privileged checker.

The object holds no-follow directory/file descriptors for the original protected
plan, archived plan/events/response, deployed bootstrap runner/parser and CA bundle.
The original plan must match the installed manifest/account and fixed host source
selection. Files require root ownership, exact modes, one hard link, bounded size
and exact selected bytes. Scope storage must remain root0700. The large response
is checked through a bounded descriptor read without raising the installed
verifier's one-MiB code/manifest limit or modifying installed code.

Every verification checks root installation/account custody, file bytes and inode,
mode, owner, size and change timestamps, source route/private address/WAN MAC, host
boot/namespaces and a structural network fingerprint. File checks bracket local
network reads. Only previously defined counter/lifetime fields are normalized;
new rules, addresses, routes or changed policies are not ignored. Any observed
failure closes all held descriptors permanently. A later `verify()` on that object
is refused, including after the underlying condition is repaired.

The fingerprint includes file identities and exact source hashes; two observations
can compare the same binding without including changing process IDs or observation
times. `--expect-binding` rejects a different selected fingerprint. Observation
reports are not serialized capabilities and cannot recreate held descriptors or
issue a dispatch permit. There is no reset, signing, activation or transport API.

## Actual acceptance

Reviewed checker bytes were staged root0444 at
`/run/trader-egress-install-20260916/authority_binding.py`, SHA256
`17e345b87691506e33f6a69037b61ff21d0b6b21a5a6c1a372dc740bf468c634`.
The existing installed sources, manifest, consumed scopes and firewall were not
modified. The temporary staging directory is not a new recurring service.

Two fresh root processes checked the original plan/events/response pins from the
immutable bootstrap result. The second required the first fingerprint and matched:
`ba885da2194a326c12ff7e1eef26fd51f1c9d500c2ddda1279caa49a44d85701`.
Their report bytes differ only in observation times; the complete bindings match.
A third read with a deliberately wrong expected fingerprint returned refusal.

The raw observations and acceptance result remain private; their hashes are pinned
in the [result JSON](portfolio-local-authority-binding-2026-09-16.json).
Original root-owned plan/events/response were rechecked against retained exports
and are unchanged. sing-box, Docker and tailscaled remain active. There were zero
venue requests and zero network mutations.

## Use and limits

```bash
sudo -n /usr/bin/python3 -I ROOT-STAGED-REVIEWED-authority_binding.py \
  --plan-sha256 ORIGINAL-PLAN-SHA256 \
  --events-sha256 ORIGINAL-EVENTS-SHA256 \
  --response-sha256 ORIGINAL-RESPONSE-SHA256 \
  --expect-binding PREVIOUSLY-SELECTED-BINDING-SHA256
```

Omit the last option only for the initial read-only observation. The caller may
retain stdout in a new private report. Exit 2 means local custody was verified,
with network admission still false; exit 1 means refusal. The underlying reusable
`AuthorityBinding` owns and permanently invalidates its installation handles.

This establishes **current local root custody** and consistency with a selected
historical plan. It does not reauthenticate the venue, prove that root never
modified historical bytes, resist a malicious administrator/kernel, establish
cloud NAT independently, or turn a local source/gateway key into an independent
qualified authority. No signing keys were created and no archived claim was
retroactively signed. Current network reads are observations, not continuous
traffic accounting or a future enforcement promise. Reboot, storage rollback,
power-loss durability and the stale counter/unknown-usage blockers remain.

Next implement prospective all-caller accounting and dispatch enforcement that
uses held local custody and explicit source/gateway authority policy. It must
account for failed/uncertain attempts, full applicable history and future bounds,
and invalidate coverage on route/rule/storage/account drift. Test that integration
locally before proposing any new concrete maintenance scope. The consumed 20-second
bootstrap window supplies no authorization for another or longer interruption.
The frozen joint budget stays 17 GETs / 468 weight; joint admission and trading
remain blocked, strict continuity 0/14.

Verification: **22 new / 100 focused Python tests pass**. Cases include same-byte
file replacement, altered bytes, symlink/hardlink/FIFO, ancestor replacement,
permissions, installed parser/CA change, account/boot/MAC/route/nft drift, mutation
during network reads, wrong initial pins, failed reads, descriptor cleanup and
permanent invalidation. Counter/lifetime-only changes preserve the binding. Actual
host acceptance adds two matching independent processes and wrong-selection
refusal. An initial fixture setup tried to overwrite its own read-only source;
that setup was corrected before the passing run. Ruff/format, evidence pins,
frozen artifacts, links and diff checks pass. No upstream code or live order path
changed; project status and reading index are updated. Unchanged kernel harnesses
and full application regression were not rerun.
