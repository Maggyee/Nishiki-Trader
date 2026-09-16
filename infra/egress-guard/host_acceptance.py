"""Explicit inactive host acceptance; stage reviewed bytes under root ownership.

Fixed installation and fixed acceptance record only. No host network change,
transport, service, credential or real collection-scope operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path

CODE = Path("/usr/local/lib/trader-egress")
STORAGE = Path("/var/lib/trader/egress")
RECORD_ROOT = STORAGE / "installation-acceptance-v1"
RECORD = RECORD_ROOT / "consumed.json"
AUTHORITY_UID = 0
ENTRY_HASH = "2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(raw):
    scope = {"__name__": "trusted_host_acceptance"}
    exec(compile(raw, "<verified-source>", "exec"), scope)
    return scope


def directory_sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_exclusive(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def installation():
    # Bootstrap only the exact previously reviewed entry bytes, after verifying
    # protected root-owned ancestors. The entry validates the verifier before exec.
    for path in (Path("/"), Path("/usr"), Path("/usr/local"), Path("/usr/local/lib"), CODE):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != AUTHORITY_UID or info.st_mode & 0o022:
            raise ValueError("untrusted_installed_ancestor")
    fd = os.open(CODE / "helper_entry.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != AUTHORITY_UID
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o444
        ):
            raise ValueError("untrusted_installed_entry")
        raw = os.pread(fd, 1024 * 1024 + 1, 0)
        if digest(raw) != ENTRY_HASH:
            raise ValueError("entry_pin_changed")
    finally:
        os.close(fd)
    return load(raw)["load_verifier"]()()


def prepare_record(authority):
    authority.verify()
    RECORD_ROOT.mkdir(mode=0o700)  # Existing/partial acceptance cannot be reset.
    directory_sync(STORAGE)
    write_exclusive(
        RECORD_ROOT / "README.md",
        b"Inactive host installation acceptance only. Phase: permissions and process restart. No collection or trading scope. Next: verify the original consumed.json using its retained SHA256. Never reset this directory.\n",
    )
    raw = (
        json.dumps(
            {
                "schema_version": "portfolio.egress_host_acceptance_record.v1",
                "fixture_only": True,
                "consumed": True,
                "manifest_sha256": authority.manifest_sha256,
                "account": authority.account,
                "created_ns": time.time_ns(),
                "helper_pid": os.getpid(),
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    write_exclusive(RECORD, raw)
    directory_sync(RECORD_ROOT)
    return digest(raw)


def read_record(expected):
    info = RECORD_ROOT.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != AUTHORITY_UID
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("acceptance_directory_authority")
    fd = os.open(RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != AUTHORITY_UID
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("acceptance_record_authority")
        raw = os.pread(fd, 4097, 0)
        if len(raw) > 4096 or digest(raw) != expected:
            raise ValueError("acceptance_record_hash")
        return json.loads(raw)
    finally:
        os.close(fd)


PROBE = r"""
import errno,json,os
from pathlib import Path
checks=[]
def denied(name,operation):
 try: fd=operation()
 except OSError as exc:
  if exc.errno not in (errno.EACCES,errno.EPERM): raise
  checks.append(name)
 else:
  if isinstance(fd,int): os.close(fd)
  raise RuntimeError('unexpected access:'+name)
for name in ('collector_launcher.py','inspect_binding.py','installation.py','helper_entry.py'):
 path=Path('/usr/local/lib/trader-egress')/name
 if not path.read_bytes(): raise RuntimeError('source unreadable')
 denied('write_code:'+name,lambda:os.open(path,os.O_WRONLY))
for path in ('/etc/trader/egress-install.json','/var/lib/trader/egress/installation-acceptance-v1/consumed.json'):
 denied('read:'+path,lambda:os.open(path,os.O_RDONLY))
 denied('write:'+path,lambda:os.open(path,os.O_WRONLY))
denied('list_storage',lambda:os.listdir('/var/lib/trader/egress'))
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'groups':os.getgroups(),'denied':checks}))
"""


def acceptance(phase, expected=None):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError("root_required")
    authority = installation()
    try:
        if phase == "prepare":
            expected = prepare_record(authority)
        record = read_record(expected)
        if (
            record.get("account") != authority.account
            or record.get("manifest_sha256") != authority.manifest_sha256
            or record.get("consumed") is not True
            or record.get("fixture_only") is not True
        ):
            raise ValueError("acceptance_record_binding")
        launcher = load(authority.source("collector_launcher.py"))
        child = launcher["FixtureCollector"].from_installation(authority)
        try:
            identity = child.selected["process"]
            if child.observe() != {"ok": True}:
                raise ValueError("collector_observation_failed")
            try:
                child.observe()
            except RuntimeError:
                pass
            else:
                raise ValueError("collector_repeat_allowed")
        finally:
            child.close()
        if child.process.returncode != 0 or child.pidfd is not None:
            raise ValueError("collector_cleanup_failed")
        account = authority.account
        result = subprocess.run(
            [
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
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            env=ENV,
            cwd="/",
        )
        probe = json.loads(result.stdout)
        if probe["uid"] != account["uid"] or probe["gid"] != account["gid"] or probe["groups"]:
            raise ValueError("probe_identity")
        authority.verify()
        if read_record(expected) != record:
            raise ValueError("acceptance_record_changed")
        return {
            "schema_version": "portfolio.egress_host_acceptance.v1",
            "status": "host_installation_acceptance_passed",
            "phase": phase,
            "helper_pid": os.getpid(),
            "record_sha256": expected,
            "manifest_sha256": authority.manifest_sha256,
            "account": account,
            "collector_identity": identity,
            "permission_probe": probe,
            "repeat_observation_refused": True,
            "record_unchanged": True,
            "host_network_modified": False,
            "process_restart_verified": phase == "verify"
            and record["helper_pid"] != os.getpid()
            and record["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "host_reboot_verified": False,
            "power_loss_durability_verified": False,
            "network_admitted": False,
            "venue_requests_made": 0,
        }
    finally:
        authority.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "verify"), required=True)
    parser.add_argument("--record-sha256")
    args = parser.parse_args(argv)
    if (args.phase == "verify") != (args.record_sha256 is not None):
        parser.error("verify requires the original record hash; prepare accepts none")
    try:
        result = acceptance(args.phase, args.record_sha256)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "status": "host_acceptance_blocked",
                    "error_type": type(exc).__name__,
                    "network_admitted": False,
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
