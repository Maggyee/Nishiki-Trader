"""Disposable fixed installation/UID gateway integration; never install on the host."""

from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
import time
from pathlib import Path

SCENARIOS = ("success", "code_drift", "account_drift", "storage_drift", "controller_crash")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def load(raw):
    scope = {"__name__": "installed_gateway_acceptance"}
    exec(compile(raw, "<fixed-fixture-source>", "exec"), scope)
    return scope


PROBE = r"""
import errno,json,os,socket
from pathlib import Path
checks=[]
def denied(name, operation):
    try:
        result=operation()
    except OSError as exc:
        if exc.errno not in (errno.EACCES,errno.EPERM): raise
        checks.append(name)
    else:
        if isinstance(result,int): os.close(result)
        raise RuntimeError('unexpected_permission:'+name)
code=Path('/usr/local/lib/trader-egress')
for name in ('installed_gateway.py','ledger_gateway.py','selftest.py','portfolio_rate_evidence.py','portfolio_tls_provenance.py','portfolio_egress_ledger.py'):
    path=code/name
    assert path.read_bytes()
    denied('write:'+name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink:'+name,lambda:os.unlink(path))
    denied('chmod:'+name,lambda:os.chmod(path,0o644))
for path in (Path('/etc/trader/egress-gateway-fixture.json'),Path('/run/trader-egress-gateway-fixture.json'),Path('/var/lib/trader/egress/local-egress-attempts-v1/events.jsonl'),Path('/var/lib/trader/egress/local-egress-attempts-v1/kernel.jsonl')):
    denied('read:'+path.name,lambda:os.open(path,os.O_RDONLY))
    denied('write:'+path.name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink:'+path.name,lambda:os.unlink(path))
denied('create_alternative_scope',lambda:os.mkdir('/var/lib/trader/egress/replacement'))
with socket.socket() as s:
    denied('forge_socket_mark',lambda:s.setsockopt(socket.SOL_SOCKET,socket.SO_MARK,29810))
with socket.socket() as s:
    s.settimeout(0.3)
    try: s.connect(('198.51.100.2',23456))
    except (TimeoutError,PermissionError): checks.append('unmarked_egress_denied')
    else: raise RuntimeError('unmarked_egress_allowed')
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines())
assert os.getuid()!=0 and status['Groups'].strip()=='' and status['NoNewPrivs'].strip()=='1'
assert all(int(status[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
print(json.dumps({'checks':checks,'uid':os.getuid(),'gid':os.getgid()}))
"""


def worker(payload):
    base = load(payload["base_source"])
    base["require_isolation"](payload["original"])
    if payload["scenario"] not in SCENARIOS:
        raise ValueError("unknown_fixture_scenario")
    # The existing pinned installer and its 40 checks run before extension staging.
    installed = base["worker"](payload)
    signal.alarm(60)
    run, write = base["run"], base["write"]
    entry = load(payload["sources"]["installed_gateway.py"])
    if set(payload["sources"]) != set(entry["FILES"]):
        raise ValueError("fixture_source_inventory")
    pins = {name: base["sha"](raw.encode()) for name, raw in payload["sources"].items()}
    if pins != payload["source_sha256"]:
        raise ValueError("fixture_source_selection")
    for name in entry["FILES"]:
        write(entry["CODE"] + "/" + name, payload["sources"][name].encode(), 0o444)
    base_manifest = Path("/etc/trader/egress-install.json").read_bytes()
    manifest = {
        "schema_version": entry["PROFILE"],
        "base_manifest_sha256": base["sha"](base_manifest),
        "files": pins,
    }
    write(entry["MANIFEST"], json.dumps(manifest, sort_keys=True).encode(), 0o600)
    write(
        entry["CONTEXT"],
        json.dumps(
            {
                "profile": entry["PROFILE"],
                "original": payload["original"],
                "isolated": base["namespaces"](),
            },
            sort_keys=True,
        ).encode(),
        0o600,
    )
    guards = load(payload["sources"]["selftest.py"])
    gateway = load(payload["sources"]["ledger_gateway.py"])
    ledger_module = gateway["load_ledger"](payload["sources"])
    peer = guards["Child"](payload["sources"]["selftest.py"])
    controller = None
    try:
        ip, nft, network_run = guards["IP"], guards["NFT"], guards["run"]
        network_run(ip, "link", "set", "lo", "up")
        network_run(ip, "link", "add", "wan", "type", "veth", "peer", "name", "peer")
        network_run(ip, "link", "set", "peer", "netns", str(peer.process.pid))
        network_run(ip, "link", "set", "wan", "up")
        network_run(ip, "address", "add", "198.51.100.1/24", "dev", "wan")
        peer.ip("link", "set", "peer", "up")
        for address in ("198.51.100.2/24", "198.51.100.3/24"):
            peer.ip("address", "add", address, "dev", "peer")
        for address in ("fd00:7472:2::2/64", "fd00:7472:2::3/64"):
            peer.ip("-6", "address", "add", address, "dev", "peer", "nodad")
        if peer.request({"action": "serve"}) != {"ok": True}:
            raise RuntimeError("fixture_peer_not_ready")
        network_run(nft, "-f", "-", text=gateway["RULES"])
        command = ["/usr/bin/python3", "-I", entry["CODE"] + "/installed_gateway.py", "--fixture"]
        controller = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=ENV,
            cwd="/",
        )
        line = controller.stdout.readline()
        if not line:
            raise RuntimeError("installed_controller_not_ready:" + controller.stderr.read()[-3000:])
        ready = json.loads(line)
        if ready["stage"] != "activated":
            raise RuntimeError("installed_controller_wrong_stage")
        identity = ready["binding"]["collector"]["process"]
        account = installed["fixture_account"]
        if (
            identity["uids"] != [account["uid"]] * 4
            or identity["gids"] != [account["gid"]] * 4
            or identity["groups"]
        ):
            raise RuntimeError("installed_collector_identity")
        descriptors = [os.readlink(p) for p in Path(f"/proc/{identity['pid']}/fd").iterdir()]
        if any(
            any(
                prefix in target
                for prefix in ("/var/lib/trader", entry["CODE"], "/etc/trader", entry["CONTEXT"])
            )
            for target in descriptors
        ):
            raise RuntimeError("privileged_file_descriptor_inherited")
        checks = [
            "fixed_root_owned_sources_and_manifest_loaded",
            "distinct_uid_authenticated_before_preparation",
            "collector_has_no_privileged_file_descriptors",
        ]

        def denied_counter():
            rows = json.loads(
                network_run(
                    nft, "-j", "list", "counter", "inet", "fixture_ledger_gateway", "output_denied"
                )
            )
            return next(row["counter"]["packets"] for row in rows["nftables"] if "counter" in row)

        before = denied_counter()
        probe = json.loads(
            run(
                "/usr/bin/setpriv",
                f"--reuid={account['uid']}",
                f"--regid={account['gid']}",
                "--clear-groups",
                "--bounding-set=-all",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "/usr/bin/python3",
                "-I",
                "-c",
                PROBE,
            )
        )
        if (probe["uid"], probe["gid"]) != (
            account["uid"],
            account["gid"],
        ) or denied_counter() <= before:
            raise RuntimeError("dedicated_uid_or_packet_denial_missing")
        checks.extend(probe["checks"])
        scenario = payload["scenario"]
        restore = None
        if scenario == "code_drift":
            target = Path(entry["CODE"]) / "ledger_gateway.py"
            original = target.read_bytes()
            target.write_bytes(original + b"\n# injected fixture drift\n")

            def restore():
                target.write_bytes(original)
        elif scenario == "account_drift":
            target = Path("/etc/group")
            original = target.read_bytes()
            target.write_bytes(original + b"foreign:x:22000:trader-egress\n")

            def restore():
                target.write_bytes(original)
        elif scenario == "storage_drift":
            target = Path(entry["STORAGE"])
            target.chmod(0o755)

            def restore():
                target.chmod(0o700)

        if scenario == "controller_crash":
            controller.kill()
            stdout, stderr = controller.communicate(timeout=5)
            if controller.returncode != -signal.SIGKILL:
                raise RuntimeError("controller_sigkill_failed")
            rows = json.loads(
                network_run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if not any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("crash_permission_not_observed")
            time.sleep(5.2)
            terminal = {"status": "controller_sigkill", "revoked": None}
            checks.append("controller_death_retains_permit_until_kernel_expiry")
        else:
            stdout, stderr = controller.communicate("continue\n", timeout=10)
            if controller.returncode:
                raise RuntimeError("installed_controller_failed:" + stderr[-3000:])
            terminal = json.loads(stdout)
            if (
                terminal["status"]
                != ("fixture_echo_succeeded" if scenario == "success" else "refused")
                or not terminal["revoked"]
            ):
                raise RuntimeError("wrong_installed_gateway_outcome")
        if restore is not None:
            restore()
        before = denied_counter()
        try:
            gateway["marked_echo"]()
        except OSError:
            pass
        else:
            raise RuntimeError("marked_socket_not_denied_after_terminal")
        if denied_counter() <= before:
            raise RuntimeError("terminal_deny_counter_missing")
        checks.append("marked_socket_kernel_denied_after_terminal_or_expiry")
        scope = Path(entry["STORAGE"]) / ledger_module.SCOPE
        attempts, lifecycle = (
            (scope / "events.jsonl").read_bytes(),
            (scope / "kernel.jsonl").read_bytes(),
        )
        attempt_report = ledger_module.replay(
            attempts,
            expected_sha256=ledger_module.digest(attempts),
            binding_sha256=ready["binding_sha256"],
        )
        life_report = gateway["replay_lifecycle"](
            ledger_module,
            lifecycle,
            expected_sha256=ledger_module.digest(lifecycle),
            attempts=attempts,
            binding_sha256=ready["binding_sha256"],
        )
        if attempt_report["pending_attempt"] != (None if scenario == "success" else 0):
            raise RuntimeError("pending_attempt_lost")
        if life_report["revocation_recorded"] != (
            scenario not in {"controller_crash", "storage_drift"}
        ):
            raise RuntimeError("invented_or_missing_revocation_record")
        restarted = subprocess.run(
            command,
            input="continue\n",
            capture_output=True,
            text=True,
            env=ENV,
            cwd="/",
            timeout=10,
        )
        if (
            restarted.returncode != 1
            or "FileExistsError" not in restarted.stderr
            or restarted.stdout
        ):
            raise RuntimeError("fresh_installed_process_reopened_consumed_scope")
        if (scope / "events.jsonl").read_bytes() != attempts or (
            scope / "kernel.jsonl"
        ).read_bytes() != lifecycle:
            raise RuntimeError("restart_changed_original_journals")
        checks.append("fresh_installed_process_refuses_scope_without_changing_journals")
        if (
            Path(entry["STORAGE"] + "/consumed.json").read_bytes()
            != b'{"fixture_only":true,"consumed":true}\n'
        ):
            raise RuntimeError("prior_consumed_fixture_state_changed")
        checks.append("prior_consumed_fixture_state_preserved")
        return {
            "scenario": scenario,
            "status": "passed",
            "checks": checks,
            "base_installation": installed,
            "gateway_manifest": manifest,
            "gateway_manifest_sha256": base["sha"](Path(entry["MANIFEST"]).read_bytes()),
            "binding": ready["binding"],
            "binding_sha256": ready["binding_sha256"],
            "terminal": terminal,
            "attempt_archive": attempts.decode(),
            "lifecycle_archive": lifecycle.decode(),
            "attempt_replay": attempt_report,
            "lifecycle_replay": life_report,
        }
    finally:
        if controller is not None and controller.poll() is None:
            controller.kill()
            controller.communicate(timeout=3)
        peer.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the disposable wrapper as an ordinary user")
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        directory = Path(__file__).resolve().parent
        base_source = (directory / "installation_selftest.py").read_text()
        base = load(base_source)
        installer = (directory / "package.py").read_bytes()
        if base["sha"](installer) != base["INSTALLER_PIN"]:
            raise ValueError("reviewed_installer_changed")
        package = load(installer)
        package["build"].__globals__["__file__"] = str(directory / "package.py")
        bundle = package["build"]()
        package["inspect"](bundle, base["PIN"])
        entry = load((directory / "installed_gateway.py").read_bytes())
        sources = {
            name: (
                (
                    directory.parents[1] / "apps/strategies_nautilus"
                    if name.startswith("portfolio_")
                    else directory
                )
                / name
            ).read_text()
            for name in entry["FILES"]
        }
        payload = {
            "source": Path(__file__).read_text(),
            "base_source": base_source,
            "installer": installer.decode(),
            "bundle": base64.b64encode(bundle).decode(),
            "original": base["namespaces"](),
            "sources": sources,
            "source_sha256": {name: base["sha"](raw.encode()) for name, raw in sources.items()},
        }
        before = base["host_observation"]()
        reports = []
        bootstrap = "import json,sys\np=json.load(sys.stdin)\ns={'__name__':'isolated_installed_gateway'}\nexec(compile(p['source'],'<fixture>','exec'),s)\nprint(json.dumps(s['worker'](p),sort_keys=True))\n"
        for scenario in SCENARIOS:
            command = [
                "/usr/bin/sudo",
                "-n",
                "/usr/bin/unshare",
                "--mount",
                "--net",
                "--pid",
                "--fork",
                "--kill-child",
                "--mount-proc",
                "--propagation",
                "private",
                "/usr/bin/python3",
                "-I",
                "-c",
                bootstrap,
            ]
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=ENV,
                cwd="/",
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(
                    json.dumps({**payload, "scenario": scenario}), timeout=70
                )
            except BaseException:
                subprocess.run(
                    ["/usr/bin/sudo", "-n", "/usr/bin/kill", "-KILL", "--", f"-{process.pid}"],
                    capture_output=True,
                    env=ENV,
                    timeout=5,
                    check=False,
                )
                process.communicate(timeout=5)
                raise
            if base["namespaces"]() != payload["original"] or base["host_observation"]() != before:
                raise RuntimeError("host_observation_changed")
            if process.returncode:
                raise RuntimeError(scenario + ":" + stderr[-5000:])
            report = json.loads(stdout)
            if report["status"] != "passed" or report["scenario"] != scenario:
                raise RuntimeError("invalid_installed_gateway_report")
            reports.append(report)
        result = {
            "schema_version": "portfolio.installed_gateway_acceptance.v1",
            "status": "passed",
            "scenarios": reports,
            "source_sha256": payload["source_sha256"],
            "harness_sha256": base["sha"](payload["source"].encode()),
            "base_harness_sha256": base["sha"](base_source.encode()),
            "bundle_sha256": base["PIN"],
            "host_observations_unchanged": True,
            "host_before_after": before,
            "host_installation_performed": False,
            "venue_requests": 0,
            "power_loss_qualified": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
            "trading_admitted": False,
        }
        raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "scenarios": len(reports),
                "checks_per_scenario": [len(row["checks"]) for row in reports],
                "report_sha256": base["sha"](raw),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
