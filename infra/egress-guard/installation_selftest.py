"""Explicit sudo-backed disposable installation/UID acceptance; no host installation.

Run as an ordinary user with --report NEW_FILE. Only reviewed fixed fixture code
runs under sudo in fresh private mount/network/PID namespaces. No sudo rule is
created and there is no privileged host-operation interface.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path

PIN = "995380e089df6c658a2ee7fa8224441d6173ed08b9656fc6447fad85d62800ec"
INSTALLER_PIN = "7f519e26c0f85951e8d60f8cf8eaa6e774fb002c74647ee4892b491cef8b549d"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
PYTHON = "/usr/bin/python3"
MOUNTS = ("/etc", "/run", "/usr/local/lib", "/var/lib", "/var/log", "/var/mail", "/tmp")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def namespaces():
    return {key: os.readlink("/proc/self/ns/" + key) for key in ("mnt", "net", "pid")}


def host_observation():
    result = {"account_hashes": {}, "installation_paths": {}}
    for path in ("/etc/passwd", "/etc/group"):
        result["account_hashes"][path] = sha(Path(path).read_bytes())
    for path in (
        "/usr/local/lib/trader-egress",
        "/etc/trader/egress-install.json",
        "/var/lib/trader/egress",
    ):
        try:
            info = os.lstat(path)
            result["installation_paths"][path] = [
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_uid,
                info.st_gid,
            ]
        except FileNotFoundError:
            result["installation_paths"][path] = "missing"
        except PermissionError:
            result["installation_paths"][path] = "unreadable"
    return result


def require_isolation(original):
    if os.getuid() != 0 or os.geteuid() != 0 or os.getpid() != 1:
        raise RuntimeError("disposable_root_pid1_required")
    current = namespaces()
    if set(original) != set(current) or any(current[key] == original[key] for key in current):
        raise RuntimeError("fresh_namespaces_required")
    return current


def run(*args, expected=0):
    result = subprocess.run(args, env=ENV, cwd="/", capture_output=True, text=True, timeout=10)
    if result.returncode != expected:
        raise RuntimeError(
            "fixture_command_failed:"
            + Path(args[0]).name
            + ":"
            + result.stderr[-2000:]
            + result.stdout[-1000:]
        )
    return result.stdout


def write(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def load(raw):
    scope = {"__name__": "isolated_installation_acceptance"}
    exec(compile(raw, "<reviewed-fixture>", "exec"), scope)
    return scope


# Fixed probe, separate from the installed collector's finite control protocol.
# Failed permissions are tested by kernel operations, never inferred from mode bits.
PERMISSION_PROBE = r"""
import errno,json,os
from pathlib import Path
checks=[]
def denied(name, operation):
    try:
        result=operation()
    except OSError as exc:
        if exc.errno not in (errno.EACCES,errno.EPERM):
            raise
        checks.append(name)
    else:
        if isinstance(result,int): os.close(result)
        raise RuntimeError('unexpected_permission:'+name)
code=Path('/usr/local/lib/trader-egress')
for name in ('collector_launcher.py','inspect_binding.py','installation.py','helper_entry.py'):
    path=code/name
    if not path.read_bytes(): raise RuntimeError('code_unreadable')
    checks.append('read_code:'+name)
    denied('write_code:'+name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink_code:'+name,lambda:os.unlink(path))
    denied('chmod_code:'+name,lambda:os.chmod(path,0o644))
manifest=Path('/etc/trader/egress-install.json')
denied('read_manifest',lambda:os.open(manifest,os.O_RDONLY))
denied('write_manifest',lambda:os.open(manifest,os.O_WRONLY))
denied('replace_manifest',lambda:os.unlink(manifest))
root=Path('/var/lib/trader/egress')
denied('list_storage',lambda:os.listdir(root))
denied('read_consumed',lambda:os.open(root/'consumed.json',os.O_RDONLY))
denied('write_consumed',lambda:os.open(root/'consumed.json',os.O_WRONLY))
denied('delete_consumed',lambda:os.unlink(root/'consumed.json'))
denied('create_scope',lambda:os.mkdir(root/'new-scope'))
denied('replace_code_directory',lambda:os.rename(code,code.with_name('moved')))
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines())
assert os.getuid()!=0 and status['Groups'].strip()==''
assert status['NoNewPrivs'].strip()=='1'
assert all(int(status[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
print(json.dumps({'checks':checks,'uid':os.getuid(),'gid':os.getgid()}))
"""


def worker(payload):
    def expired(_signal, _frame):
        raise TimeoutError("installation_fixture_deadline")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(45)
    original = payload["original"]
    isolated = require_isolation(original)
    checks = ["fresh_root_mount_network_pid_namespaces"]
    # Propagation becomes private before any temporary mount. Abort on failure.
    run("/usr/bin/mount", "--make-rprivate", "/")
    for target in MOUNTS:
        if not Path(target).is_dir() or Path(target).is_symlink():
            raise RuntimeError("fixture_mount_target_missing_or_symlink")
    for target in MOUNTS:
        run(
            "/usr/bin/mount",
            "-t",
            "tmpfs",
            "-o",
            "size=16m,mode=0755,nosuid,nodev",
            "tmpfs",
            target,
        )
    os.chmod("/tmp", 0o1777)
    # Never copy the host passwd/shadow databases. useradd acts on synthetic local
    # files in the private mount namespace, choosing actual nonzero kernel IDs.
    for name, raw, mode in (
        ("passwd", b"root:x:0:0:root:/root:/bin/bash\n", 0o644),
        ("group", b"root:x:0:\n", 0o644),
        ("shadow", b"root:!:20000:0:99999:7:::\n", 0o600),
        ("gshadow", b"root:!::\n", 0o600),
        ("nsswitch.conf", b"passwd: files\ngroup: files\nshadow: files\nhosts: files\n", 0o644),
        (
            "login.defs",
            b"SYS_UID_MIN 20000\nSYS_UID_MAX 20999\nSYS_GID_MIN 20000\nSYS_GID_MAX 20999\n",
            0o644,
        ),
    ):
        write("/etc/" + name, raw, mode)
    Path("/etc/default").mkdir()
    write("/etc/default/useradd", b"CREATE_MAIL_SPOOL=yes\n", 0o644)
    # No interface is brought up, no route or external socket is created.
    interfaces = json.loads(run("/usr/sbin/ip", "-j", "link", "show"))
    if [row["ifname"] for row in interfaces] != ["lo"]:
        raise RuntimeError("unexpected_fixture_interface")
    checks.append("synthetic_account_database_and_no_external_interface")
    raw = base64.b64decode(payload["bundle"], validate=True)
    installer = payload["installer"].encode()
    if sha(raw) != PIN or sha(installer) != INSTALLER_PIN:
        raise RuntimeError("reviewed_bundle_hash_mismatch")
    package = load(installer)
    contents = package["inspect"](raw, PIN)
    if contents["install.py"] != installer:
        raise RuntimeError("installer_mismatch")
    staging = Path("/run/trader-egress-review")
    staging.mkdir(mode=0o755)
    write(
        staging / "README.md",
        b"Disposable installation fixture. No host deployment. Next: fixed installer and check only.\n",
        0o444,
    )
    write(staging / "install.py", installer, 0o444)
    write(staging / "bundle.tar", raw, 0o444)
    storage = Path("/var/lib/trader/egress")
    storage.mkdir(parents=True, mode=0o700)
    consumed = storage / "consumed.json"
    consumed_raw = b'{"fixture_only":true,"consumed":true}\n'
    write(consumed, consumed_raw, 0o600)
    install_args = (
        PYTHON,
        "-I",
        str(staging / "install.py"),
        "apply",
        "--bundle",
        str(staging / "bundle.tar"),
        "--sha256",
        PIN,
    )
    result = json.loads(run(*install_args))
    if result["status"] != "installed_inactive" or result["network_admitted"]:
        raise RuntimeError("unexpected_installer_result")
    checks.extend(["actual_useradd_and_password_lock", "reviewed_first_install_succeeds"])
    if list(Path("/var/mail").iterdir()) or list(Path("/var/log").iterdir()):
        raise RuntimeError("unexpected_mail_or_login_log")
    checks.append("system_account_creates_no_mail_or_login_log")
    entry_args = (PYTHON, "-I", "/usr/local/lib/trader-egress/helper_entry.py", "--check")
    entry = json.loads(run(*entry_args, expected=2))
    if entry["status"] != "installation_verified_inactive" or entry["collector_started"]:
        raise RuntimeError("installed_entry_not_inactive")
    checks.append("fresh_process_fixed_installed_check")
    verifier = load(contents["installation.py"])
    installation = verifier["TrustedInstallation"]()
    account = installation.account
    launcher = load(installation.source("collector_launcher.py"))
    collector = launcher["FixtureCollector"].from_installation(installation)
    try:
        process = collector.selected["process"]
        if process["uids"] != [account["uid"]] * 4 or account["uid"] == os.getuid():
            raise RuntimeError("same_uid_fixture_forbidden")
        checks.append("actual_distinct_uid_kernel_credentials_and_pidfd")
        if collector.observe() != {"ok": True}:
            raise RuntimeError("observation_failed")
        checks.append("authenticated_one_observation")
        try:
            collector.observe()
        except RuntimeError:
            checks.append("repeat_observation_refused")
        else:
            raise RuntimeError("repeat_observation_allowed")
    finally:
        collector.close()
    if collector.process.returncode != 0 or collector.pidfd is not None:
        raise RuntimeError("collector_cleanup_failed")
    checks.append("collector_exit_and_descriptor_cleanup")
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
            PYTHON,
            "-I",
            "-c",
            PERMISSION_PROBE,
        )
    )
    if (probe["uid"], probe["gid"]) != (account["uid"], account["gid"]):
        raise RuntimeError("probe_wrong_identity")
    checks.extend(probe["checks"])
    installation.verify()
    if consumed.read_bytes() != consumed_raw:
        raise RuntimeError("consumed_storage_changed")
    checks.append("original_consumed_bytes_preserved")
    refused = json.loads(run(*install_args, expected=1))
    if refused["status"] != "bundle_operation_failed" or consumed.read_bytes() != consumed_raw:
        raise RuntimeError("reinstall_not_refused")
    checks.append("actual_reinstall_refusal_preserves_state")
    storage.chmod(0o755)
    try:
        blocked = json.loads(run(*entry_args, expected=2))
        if blocked["status"] != "installation_check_blocked":
            raise RuntimeError("storage_drift_not_blocked")
        try:
            installation.verify()
        except ValueError:
            checks.append("storage_drift_invalidates_held_authority")
        else:
            raise RuntimeError("held_authority_survived_drift")
    finally:
        storage.chmod(0o700)
    try:
        installation.verify()
    except ValueError:
        checks.append("restored_permissions_do_not_revive_authority")
    else:
        raise RuntimeError("closed_authority_revived")
    installation.close()
    # A fresh checker can observe current permissions; this does not revive the
    # original authority or grant any network/collection permission.
    final = json.loads(run(*entry_args, expected=2))
    if final["status"] != "installation_verified_inactive":
        raise RuntimeError("final_check_failed")
    checks.append("fresh_check_after_fixture_restore_stays_inactive")
    return {
        "schema_version": "portfolio.egress_installation_isolated_acceptance.v1",
        "status": "passed",
        "checks": checks,
        "bundle_sha256": PIN,
        "fixture_account": account,
        "collector_identity": process,
        "isolated_namespaces": isolated,
        "actual_distinct_uid_fixture_verified": True,
        "host_installation_performed": False,
        "host_deployment_qualified": False,
        "network_admitted": False,
        "venue_requests_made": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the bounded namespace wrapper as an ordinary user")
    # Claim output before sudo or namespace activity; never overwrite old evidence.
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as report:
        directory = Path(__file__).resolve().parent
        source = Path(__file__).read_text()
        installer = (directory / "package.py").read_bytes()
        if sha(installer) != INSTALLER_PIN:
            raise ValueError("reviewed_installer_changed")
        package = load(installer)
        # Build uses the local module path only in the nonprivileged caller.
        package["build"].__globals__["__file__"] = str(directory / "package.py")
        raw = package["build"]()
        package["inspect"](raw, PIN)
        original = namespaces()
        host_before = host_observation()
        bootstrap = "import json,sys\np=json.load(sys.stdin)\ns={'__name__':'disposable_fixture'}\nexec(compile(p['source'],'<reviewed-fixture>','exec'),s)\nprint(json.dumps(s['worker'](p),sort_keys=True))\n"
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
            PYTHON,
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
                json.dumps(
                    {
                        "source": source,
                        "installer": installer.decode(),
                        "bundle": base64.b64encode(raw).decode(),
                        "original": original,
                    }
                ),
                timeout=55,
            )
        except BaseException:
            # sudo/root descendants are reaped by PID-namespace teardown; its
            # unshare parent uses --kill-child. Also enforce the worker's alarm.
            subprocess.run(
                ["/usr/bin/sudo", "-n", "/usr/bin/kill", "-KILL", "--", f"-{process.pid}"],
                env=ENV,
                capture_output=True,
                timeout=5,
                check=False,
            )
            process.communicate(timeout=5)
            raise
        if namespaces() != original:
            raise RuntimeError("caller_namespace_changed")
        if host_observation() != host_before:
            raise RuntimeError("host_observation_changed")
        if process.returncode:
            raise RuntimeError("isolated_installation_failed:" + stderr[-3000:])
        result = json.loads(stdout)
        if result["status"] != "passed" or result["bundle_sha256"] != PIN:
            raise RuntimeError("invalid_worker_report")
        result["caller_namespaces_unchanged"] = True
        result["host_account_and_path_observations_unchanged"] = True
        result["host_before_after"] = host_before
        result["harness_sha256"] = sha(source.encode())
        raw_report = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        report.write(raw_report)
        report.flush()
        os.fsync(report.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": len(result["checks"]),
                "report_sha256": sha(raw_report),
                "host_installation_performed": False,
                "network_admitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
