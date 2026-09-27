"""Disposable installed joint-window --check acceptance; no host deployment."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

BASE_HARNESS_PIN = "e2b0e9a59cd3805ebfac2fb4b4b2c1992e8e9d2865862cf70c3876c06e42346e"
ENTRY_PIN = "db9bacd6778111afdc4a163f305361bef6da8fecab56d5ec724b0d1cb66cdc7a"
SOURCES_PIN = "2c923d4b546fd0dbcbcf57fbfc4bafdb80e103611f0f38dcd9358cb6b6dea27f"
WINDOW_INSTALLER_PIN = "6bc0a7a4bbe6915a0c3d84dfb9b4dabeea0747915a08209a5781ee0b8b028d23"
SOURCES = (
    "gateway_window_entry.py",
    "gateway_window_sources.py",
    "gateway_window_kernel.py",
    "gateway_window_custody.py",
    "gateway_window_witness.py",
    "gateway_window_activation.py",
)
CODE = Path("/usr/local/lib/trader-egress")
MANIFEST = Path("/etc/trader/joint-window-sources-v1.json")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(raw):
    scope = {"__name__": "isolated_joint_window_fixture"}
    exec(compile(raw, "<reviewed-fixture>", "exec"), scope)
    return scope


def observation(base):
    result = base["host_observation"]()
    for path in (str(MANIFEST), str(CODE / SOURCES[0])):
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
    return result


def worker(payload):
    base_source = payload["base_source"].encode()
    if sha(base_source) != BASE_HARNESS_PIN:
        raise RuntimeError("base_harness_pin_changed")
    base = load(base_source)
    sources = {name: base64.b64decode(payload["sources"][name], validate=True) for name in SOURCES}
    if set(payload["sources"]) != set(SOURCES) or any(
        sha(raw) != payload["source_sha256"][name] for name, raw in sources.items()
    ):
        raise RuntimeError("source_inventory_changed")
    if sha(sources[SOURCES[0]]) != ENTRY_PIN or sha(sources[SOURCES[1]]) != SOURCES_PIN:
        raise RuntimeError("fixed_source_pin_changed")
    base_report = base["worker"](payload)
    if base_report["status"] != "passed" or base_report["network_admitted"] is not False:
        raise RuntimeError("base_fixture_not_inactive")

    installer = payload["window_installer"].encode()
    bundle = base64.b64decode(payload["window_bundle"], validate=True)
    if sha(installer) != WINDOW_INSTALLER_PIN or sha(bundle) != payload["window_bundle_sha256"]:
        raise RuntimeError("reviewed_joint_bundle_changed")
    package = load(installer)
    contents = package["inspect"](bundle, payload["window_bundle_sha256"])
    if contents["install.py"] != installer or any(
        contents[name] != sources[name] for name in SOURCES
    ):
        raise RuntimeError("joint_bundle_source_mismatch")
    staging = Path("/run/trader-egress-review")
    installer_path = staging / "window-install.py"
    bundle_path = staging / "window-bundle.tar"
    base["write"](installer_path, installer, 0o444)
    base["write"](bundle_path, bundle, 0o444)
    install_command = (
        "/usr/bin/python3",
        "-I",
        str(installer_path),
        "apply",
        "--bundle",
        str(bundle_path),
        "--sha256",
        payload["window_bundle_sha256"],
    )
    wrong_pin_command = (*install_command[:-1], "0" * 64)
    refused_pin = json.loads(base["run"](*wrong_pin_command, expected=1))
    if (
        refused_pin["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.exists()
        or (CODE / SOURCES[0]).exists()
    ):
        raise RuntimeError("unselected_joint_bundle_wrote_files")
    wrong_mode_path = staging / "window-install-mode.py"
    base["write"](wrong_mode_path, installer, 0o600)
    wrong_mode_command = (
        "/usr/bin/python3",
        "-I",
        str(wrong_mode_path),
        *install_command[3:],
    )
    refused_mode = json.loads(base["run"](*wrong_mode_command, expected=1))
    if (
        refused_mode["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.exists()
        or (CODE / SOURCES[0]).exists()
    ):
        raise RuntimeError("unprotected_joint_installer_wrote_files")
    installed = json.loads(base["run"](*install_command))
    if installed["status"] != "joint_window_installed_inactive" or installed["network_admitted"]:
        raise RuntimeError("joint_window_installation_failed")
    command = ("/usr/bin/python3", "-I", str(CODE / SOURCES[0]), "--check")

    def checked(expected):
        report = json.loads(base["run"](*command, expected=2))
        if report["status"] != expected or any(
            value is not False for key, value in report.items() if key != "status"
        ):
            raise RuntimeError("joint_window_entry_unexpected_admission")

    checked("fixed_joint_window_sources_observed_unqualified")
    original_manifest = MANIFEST.read_bytes()
    refused = json.loads(base["run"](*install_command, expected=1))
    if (
        refused["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.read_bytes() != original_manifest
    ):
        raise RuntimeError("joint_window_repeat_install_not_refused")
    document = json.loads(original_manifest)
    document["files"][SOURCES[-1]] = "0" * 64
    with MANIFEST.open("w") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    checked("joint_window_sources_missing_or_changed")
    document["files"][SOURCES[-1]] = sha(sources[SOURCES[-1]])
    with MANIFEST.open("w") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    target = CODE / SOURCES[-1]
    target.chmod(0o600)
    checked("joint_window_sources_missing_or_changed")
    return {
        "schema_version": "portfolio.joint_window_installed_isolated_acceptance.v1",
        "status": "passed",
        "base_checks": len(base_report["checks"]),
        "checks": [
            "wrong_bundle_selection_refused_before_mutation",
            "unprotected_installer_refused_before_mutation",
            "reviewed_first_install_into_existing_base",
            "fresh_process_fixed_root_entry_remains_unqualified",
            "repeat_install_refused_without_state_change",
            "manifest_pin_drift_refused",
            "source_mode_drift_refused",
        ],
        "base_manifest_sha256": document["base_manifest_sha256"],
        "window_bundle_sha256": payload["window_bundle_sha256"],
        "window_installer_sha256": WINDOW_INSTALLER_PIN,
        "source_sha256": {name: sha(raw) for name, raw in sources.items()},
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
        parser.error("run the disposable wrapper as an ordinary user")
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        directory = Path(__file__).resolve().parent
        base_source = (directory / "installation_selftest.py").read_bytes()
        installer = (directory / "package.py").read_bytes()
        sources = {name: (directory / name).read_bytes() for name in SOURCES}
        if sha(base_source) != BASE_HARNESS_PIN:
            raise ValueError("base_harness_pin_changed")
        if sha(sources[SOURCES[0]]) != ENTRY_PIN or sha(sources[SOURCES[1]]) != SOURCES_PIN:
            raise ValueError("fixed_source_pin_changed")
        base = load(base_source)
        if sha(installer) != base["INSTALLER_PIN"]:
            raise ValueError("reviewed_installer_changed")
        base_package = load(installer)
        base_package["build"].__globals__["__file__"] = str(directory / "package.py")
        bundle = base_package["build"]()
        base_package["inspect"](bundle, base["PIN"])
        window_installer = (directory / "gateway_window_package.py").read_bytes()
        if sha(window_installer) != WINDOW_INSTALLER_PIN:
            raise ValueError("reviewed_joint_installer_changed")
        window_package = load(window_installer)
        if tuple(window_package["FILES"]) != SOURCES:
            raise ValueError("joint_bundle_fixed_sources_changed")
        window_package["build"].__globals__["__file__"] = str(
            directory / "gateway_window_package.py"
        )
        window_bundle = window_package["build"]()
        window_package["inspect"](window_bundle, sha(window_bundle))
        original = base["namespaces"]()
        before = observation(base)
        payload = {
            "source": Path(__file__).read_text(),
            "base_source": base_source.decode(),
            "installer": installer.decode(),
            "bundle": base64.b64encode(bundle).decode(),
            "window_installer": window_installer.decode(),
            "window_bundle": base64.b64encode(window_bundle).decode(),
            "window_bundle_sha256": sha(window_bundle),
            "sources": {name: base64.b64encode(raw).decode() for name, raw in sources.items()},
            "source_sha256": {name: sha(raw) for name, raw in sources.items()},
            "original": original,
        }
        bootstrap = "import json,sys\np=json.load(sys.stdin)\ns={'__name__':'joint_window_fixture'}\nexec(compile(p['source'],'<fixture>','exec'),s)\nprint(json.dumps(s['worker'](p),sort_keys=True))\n"
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
            stdout, stderr = process.communicate(json.dumps(payload), timeout=55)
        except BaseException:
            subprocess.run(
                ["/usr/bin/sudo", "-n", "/usr/bin/kill", "-KILL", "--", f"-{process.pid}"],
                env=ENV,
                capture_output=True,
                timeout=5,
                check=False,
            )
            process.communicate(timeout=5)
            raise
        if base["namespaces"]() != original or observation(base) != before:
            raise RuntimeError("host_observation_changed")
        if process.returncode:
            raise RuntimeError("isolated_joint_window_failed:" + stderr[-3000:])
        report = json.loads(stdout)
        if report["status"] != "passed" or report["source_sha256"] != payload["source_sha256"]:
            raise RuntimeError("invalid_joint_window_report")
        report["host_observations_unchanged"] = True
        report["harness_sha256"] = sha(payload["source"].encode())
        raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": len(report["checks"]),
                "report_sha256": sha(raw),
                "network_admitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
