"""Pin existing approved cron entries to a clean, pushed deployment checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from apps.ops.research_shadow_daily import PROTOCOLS
from apps.ops.research_shadow_runtime import atomic_json


def render_crontab(current: str, root: Path, deployment: Path, commit: str) -> str:
    lines = []
    found = []
    for line in current.splitlines():
        match = re.search(r" -m apps\.ops\.research_v(\d+)_shadow_daily\b", line)
        pinned = re.search(r" -m apps\.ops\.research_shadow_daily --protocol (\d+)\b", line)
        match = match or pinned
        if not match or line.lstrip().startswith("#"):
            lines.append(line)
            continue
        version = int(match[1])
        if version not in PROTOCOLS:
            lines.append(line)
            continue
        if str(root) not in line:
            raise ValueError("collector belongs to another checkout; refusing replacement")
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or any(not re.fullmatch(r"[0-9*,/\-]+", f) for f in fields[:5]):
            raise ValueError("unsupported cron schedule")
        found.append(version)
        data = root / "data" / (f"research-v{version}-forward" if version < 40 else f"research-v{version}/shadow")
        command = [str(root / ".venv/bin/python"), "-m", "apps.ops.research_shadow_daily",
                   "--protocol", str(version), "--data-base", str(root / "data"), "--expected-commit", commit]
        lines.append(" ".join(fields[:5]) + " cd " + shlex.quote(str(deployment)) + " && " +
                     shlex.join(command) + " >> " + shlex.quote(str(data / "cron.log")) + " 2>&1")
    if sorted(found) != sorted(PROTOCOLS):
        raise ValueError("expected exactly one existing cron entry per registered collector")
    return "\n".join(lines) + "\n"


def install(root: Path) -> dict:
    root = root.resolve()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    commit = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise ValueError("deploy only a clean checkout")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], cwd=root, check=True)
    current = subprocess.check_output(["crontab", "-l"], text=True)
    base = root / "data/collector-deployments"
    deployment = base / commit
    updated = render_crontab(current, root, deployment, commit)
    base.mkdir(parents=True, exist_ok=True)
    (base / "README.md").write_text(
        "# Pinned shadow collector deployments\n\nPhase 5 runtime snapshots and cron backups. "
        "No live trading. Entrypoint: apps.ops.install_shadow_collectors from the source checkout.\n")
    if not deployment.exists():
        subprocess.run(["git", "clone", "--shared", "--no-checkout", str(root), str(deployment)], check=True)
        subprocess.run(["git", "checkout", "--detach", commit], cwd=deployment, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=deployment, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=deployment, text=True).strip()
    if head != commit or dirty:
        raise ValueError("existing deployment is not the expected clean revision")
    backup = base / f"crontab-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.txt"
    with backup.open("x") as handle:
        backup.chmod(0o600)
        handle.write(current)
    if subprocess.check_output(["crontab", "-l"], text=True) != current:
        raise ValueError("crontab changed during deployment; retry after inspection")
    subprocess.run(["crontab", "-"], input=updated, text=True, check=True)
    actual = subprocess.check_output(["crontab", "-l"], text=True)
    if actual != updated:
        raise ValueError("installed crontab did not match rendered plan")
    result = {"commit": commit, "deployment": str(deployment), "backup": str(backup),
              "protocols": list(PROTOCOLS), "crontab_sha256": hashlib.sha256(actual.encode()).hexdigest(),
              "schedule_cadences_changed": False, "live_path_touched": False}
    atomic_json(base / "active.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--install", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.repo_root), indent=2))


if __name__ == "__main__":
    main()
