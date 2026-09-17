"""Fixed installed gateway fixture controller; no host or venue execution mode."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from contextlib import suppress

CODE = "/usr/local/lib/trader-egress"
MANIFEST = "/etc/trader/egress-gateway-fixture.json"
CONTEXT = "/run/trader-egress-gateway-fixture.json"
STORAGE = "/var/lib/trader/egress"
ENTRY_PIN = "2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b"
FILES = (
    "installed_gateway.py",
    "ledger_gateway.py",
    "selftest.py",
    "portfolio_rate_evidence.py",
    "portfolio_tls_provenance.py",
    "portfolio_egress_ledger.py",
)
PROFILE = "portfolio.installed_gateway_fixture.v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(raw):
    scope = {"__name__": "installed_gateway_dependency"}
    exec(compile(raw, "<installed-gateway-dependency>", "exec"), scope)
    return scope


def installation():
    """Bootstrap the independently pinned base entry through held no-follow paths."""
    fds = []
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(fd)
        for name in ("usr", "local", "lib", "trader-egress", "helper_entry.py"):
            info = os.fstat(fd)
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("untrusted_gateway_ancestor")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            if name != "helper_entry.py":
                flags |= os.O_DIRECTORY
            fd = os.open(name, flags, dir_fd=fd)
            fds.append(fd)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o444
        ):
            raise ValueError("untrusted_gateway_base_entry")
        raw = os.pread(fd, 1024 * 1024 + 1, 0)
        if digest(raw) != ENTRY_PIN:
            raise ValueError("gateway_base_entry_pin")
        return load(raw)["load_verifier"]()()
    finally:
        for fd in reversed(fds):
            os.close(fd)


class InstalledGatewaySources:
    """Extend held base installation custody with a fixed fixture-only inventory."""

    def __init__(self, authority):
        self.authority = authority
        try:
            authority.verify()
            fd = authority.open_file(MANIFEST, 0o600)
            raw = os.pread(fd, 1024 * 1024 + 1, 0)
            manifest = json.loads(raw)
            if (
                not isinstance(manifest, dict)
                or set(manifest) != {"schema_version", "base_manifest_sha256", "files"}
                or manifest["schema_version"] != PROFILE
                or manifest["base_manifest_sha256"] != authority.manifest_sha256
                or not isinstance(manifest["files"], dict)
                or set(manifest["files"]) != set(FILES)
            ):
                raise ValueError("gateway_fixture_manifest")
            self.sources = {}
            for name in FILES:
                fd = authority.open_file(CODE + "/" + name, 0o444)
                source = os.pread(fd, 1024 * 1024 + 1, 0)
                if digest(source) != manifest["files"][name]:
                    raise ValueError("gateway_installed_source_pin")
                self.sources[name] = source
            self.manifest_sha256 = digest(raw)
            authority.verify()
        except BaseException:
            authority.close()
            raise

    def source(self, name):
        self.authority.verify()
        return self.sources[name]


def fixture_context(authority):
    if os.getuid() != 0 or os.geteuid() != 0 or os.getppid() != 1:
        raise ValueError("isolated_fixture_controller_required")
    fd = authority.open_file(CONTEXT, 0o600)
    context = json.loads(os.pread(fd, 65537, 0))
    current = {name: os.readlink("/proc/self/ns/" + name) for name in ("mnt", "net", "pid")}
    if (
        set(context) != {"profile", "original", "isolated"}
        or context["profile"] != PROFILE
        or context["isolated"] != current
        or set(context["original"]) != set(current)
        or any(current[k] == context["original"][k] for k in current)
    ):
        raise ValueError("gateway_fixture_namespace_binding")
    authority.verify()


class InstalledBinding:
    def __init__(self, authority, sources, collector, guards):
        self.authority, self.sources, self.collector, self.guards = (
            authority,
            sources,
            collector,
            guards,
        )
        self.ended = False
        self.selected = self.current()
        self.pin = digest(json.dumps(self.selected, sort_keys=True, separators=(",", ":")).encode())

    def current(self):
        self.authority.verify()
        self.collector.verify()
        run = self.guards["run"]
        rules = self.guards["stable_rules"](
            json.loads(
                run(self.guards["NFT"], "-j", "list", "table", "inet", "fixture_ledger_gateway")
            )
        )
        for row in rules["nftables"]:
            if "set" in row:
                row["set"].pop("elem", None)
        return {
            "base_manifest_sha256": self.authority.manifest_sha256,
            "gateway_manifest_sha256": self.sources.manifest_sha256,
            "collector": self.collector.selected,
            "rules": rules,
            "route": json.loads(run(self.guards["IP"], "-j", "route", "get", "198.51.100.2")),
            "net": os.readlink("/proc/self/ns/net"),
        }

    def verify(self):
        if self.ended:
            raise ValueError("installed_gateway_binding_ended")
        try:
            if self.current() != self.selected:
                raise ValueError("installed_gateway_binding_drift")
            return {"binding_sha256": self.pin}
        except BaseException:
            self.ended = True
            self.authority.close()
            raise


def run_controller():
    authority = installation()
    collector = ledger = lifecycle = gateway = None
    try:
        fixture_context(authority)
        sources = InstalledGatewaySources(authority)
        gateway_code = load(sources.source("ledger_gateway.py"))
        guards = load(sources.source("selftest.py"))
        module = gateway_code["load_ledger"](
            {name: sources.source(name).decode() for name in FILES}
        )
        launcher = load(authority.source("collector_launcher.py"))
        collector = launcher["FixtureCollector"].from_installation(authority)
        binding = InstalledBinding(authority, sources, collector, guards)
        # This path cannot be chosen by the caller, collector or report contents.
        ledger = module.AttemptLedger(STORAGE, binding=binding, binding_sha256=binding.pin)
        lifecycle = gateway_code["GatewayLifecycle"](ledger, module)
        run, nft = guards["run"], guards["NFT"]

        def grant():
            run(
                nft,
                "-f",
                "-",
                text=f"add element inet fixture_ledger_gateway permits {{ {gateway_code['MARK']} timeout 5s }}\n",
            )

        def revoke():
            run(nft, "flush", "set", "inet", "fixture_ledger_gateway", "permits")
            rows = json.loads(
                run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("installed_gateway_revoke_failed")

        # Fixed fixture barrier: only the namespace parent can release this pipe.
        # There is no endpoint, source, scope, payload or renewal message.
        record = lifecycle.record

        def ready(kind, payload=None):
            record(kind, payload)
            if kind == "activated":
                print(
                    json.dumps(
                        {
                            "stage": "activated",
                            "binding": binding.selected,
                            "binding_sha256": binding.pin,
                        }
                    ),
                    flush=True,
                )
                if sys.stdin.readline() != "continue\n":
                    raise ValueError("fixture_parent_release_required")

        lifecycle.record = ready
        gateway = gateway_code["FixtureLedgerGateway"](
            ledger,
            lifecycle=lifecycle,
            authorize=collector.observe,
            grant=grant,
            send=gateway_code["marked_echo"],
            revoke=revoke,
        )
        try:
            gateway.dispatch()
        except (OSError, ValueError, RuntimeError) as exc:
            outcome = {"status": "refused", "reason": type(exc).__name__}
        else:
            outcome = {"status": "fixture_echo_succeeded"}
        with suppress(Exception):
            gateway.close()
        print(
            json.dumps({**outcome, "revoked": gateway.revoked, "network_admitted": False}),
            flush=True,
        )
    finally:
        if gateway is not None:
            with suppress(Exception):
                gateway.close()
        else:
            if lifecycle is not None:
                lifecycle.close()
            if ledger is not None:
                with suppress(Exception):
                    ledger.close()
        if collector is not None:
            with suppress(Exception):
                collector.close()
        authority.close()


def main():
    if (
        sys.argv[1:] != ["--fixture"]
        or not sys.flags.isolated
        or os.path.abspath(__file__) != CODE + "/installed_gateway.py"
    ):
        raise ValueError("fixed_installed_fixture_entry_required")
    run_controller()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
