# Joint-window read-only host installation

Phase: first installation completed 2026-09-28. This procedure publishes six
root-owned 0444 sources and one root-owned 0600 manifest alongside the existing
base installation. It does not activate nft rules, collectors, venue access or
trading. Do not repeat `apply` on the installed host; the observed outcome and
remaining blockers are in
[the host installation record](progress/portfolio-joint-window-host-installation-2026-09-28.md).

## Selection and preflight

The operator must independently select the expected whole-archive SHA256 and
the expected SHA256 of the *existing host* `/etc/trader/egress-install.json`.
Do not derive either selected value from the preflight command in the same
installation attempt. The disposable fixture's base hash is different from
the host hash. The reviewed local candidate is
`data/joint-window-review-2026-09-27-r6.tar` (observed SHA256
`5d453bfaff0933e920253212b6123c6d7da6ff23f7022d091290b1694a717f32`);
its `install.py` is observed at SHA256
`4ee75b36a3c902b571727a6383944861f13903ff251dbfb3442fcb6277614ce3`.
These observations are comparison values, not operator selection or approval.

Run from the synchronized repository checkout. Use absolute bundle paths and
fill the two `SELECTED_*` values from the independent selection. Stop on any
mismatch, missing required file, unexpected joint path or changed base helper;
do not stage files or run `apply` after a failed preflight.

```bash
BUNDLE=/home/orca/orca/projects/trader/data/joint-window-review-2026-09-27-r6.tar
SELECTED_BUNDLE_SHA256=operator_selected_archive_sha256
SELECTED_BASE_SHA256=operator_selected_host_base_manifest_sha256
printf '%s  %s\n' "$SELECTED_BUNDLE_SHA256" "$BUNDLE" | sha256sum --check -
printf '%s  %s\n' "$SELECTED_BASE_SHA256" /etc/trader/egress-install.json | sudo -n sha256sum --check -
sudo -n sha256sum /usr/local/lib/trader-egress/helper_entry.py
/usr/bin/python3 -I infra/egress-guard/gateway_window_package.py inspect --bundle "$BUNDLE" --sha256 "$SELECTED_BUNDLE_SHA256"
sudo -n /usr/bin/python3 -I /usr/local/lib/trader-egress/helper_entry.py --check
sudo -n /usr/bin/python3 -I -c '
import os, sys
code = "/usr/local/lib/trader-egress/"
names = ("gateway_window_entry.py", "gateway_window_sources.py",
         "gateway_window_kernel.py", "gateway_window_custody.py",
         "gateway_window_witness.py", "gateway_window_activation.py")
paths = ["/etc/trader/joint-window-sources-v1.json", *(code + n for n in names)]
present = [p for p in paths if os.path.lexists(p)]
print({"unexpected_joint_paths": present})
sys.exit(bool(present))
'
```

The installed helper must still hash to
`2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b`.
From an ordinary user's checkout, the existing helper's isolated root `--check`
must return exit 2 with `installation_verified_inactive` and admission false.
The final preflight checks all six joint paths and the manifest with `lexists`,
including dangling symlinks. The installer repeats this
preflight with exclusive creation. Recheck repository `main` and archive identity
immediately before staging; changes require another independent selection.

## Protected staging and first installation

For an initial installation on a host where every joint path is still absent,
only after the independent selection and separate host installation decision,
choose a **new, empty** root-owned directory under `/run` with root-owned,
non-group-writable ancestors. The following commands are an operator procedure,
not an automated deployment. A failed command stops the procedure.

```bash
umask 077
set -o noclobber
LOCAL_INSTALLER=data/joint-window-review-2026-09-27-r6-install.py
tar -xOf "$BUNDLE" install.py > "$LOCAL_INSTALLER"
printf '%s  %s\n' 4ee75b36a3c902b571727a6383944861f13903ff251dbfb3442fcb6277614ce3 "$LOCAL_INSTALLER" | sha256sum --check -
STAGE=/run/trader-egress-window-SELECTED-UNIQUE-SCOPE
sudo -n mkdir --mode=0755 -- "$STAGE"
sudo -n install -m 0444 -o root -g root "$LOCAL_INSTALLER" "$STAGE/window-install.py"
sudo -n sha256sum "$STAGE/window-install.py"
sudo -n /usr/bin/python3 -I "$STAGE/window-install.py" apply --bundle "$BUNDLE" --sha256 "$SELECTED_BUNDLE_SHA256" --base-sha256 "$SELECTED_BASE_SHA256"
```

Before `apply`, confirm the staged file is root-owned, single-link 0444 with
root-owned non-writable ancestors and the displayed staged hash equals the
installer value above. The installer checks those properties again. Do not
substitute a copied checkout script or pass an auto-observed base hash as the
selected value. Success reports `joint_window_installed_inactive`; every
admission flag must remain false.

## Post-install read-only checks

Use the same protected installer, independently selected bundle and base hash:

```bash
sudo -n /usr/bin/python3 -I "$STAGE/window-install.py" audit --bundle "$BUNDLE" --sha256 "$SELECTED_BUNDLE_SHA256" --base-sha256 "$SELECTED_BASE_SHA256"
sudo -n /usr/bin/python3 -I "$STAGE/window-install.py" check-entry --bundle "$BUNDLE" --sha256 "$SELECTED_BUNDLE_SHA256" --base-sha256 "$SELECTED_BASE_SHA256"
sudo -n /usr/bin/python3 -I /usr/local/lib/trader-egress/gateway_window_entry.py --check
```

`audit` must exit 0 with `joint_window_installed_sources_observed_inactive`.
The other two checks must exit 2 and remain unqualified. The protected
`check-entry` verifies selected installed bytes before and after executing
selected entry bytes in its own process; direct entry invocation has no
independent startup attestation. Neither result proves continuous exclusion,
mark ownership, complete caller coverage or source authentication.

If `apply` fails or any new file/manifest appears unexpectedly, **stop**. The
first source is a partial-install marker; a second `apply` must refuse. Preserve
the staging directory and installed bytes for manual inspection; do not remove,
replace or retry them automatically. Do not run blackout activation or any
collector. Further network and trading gates remain separate.
