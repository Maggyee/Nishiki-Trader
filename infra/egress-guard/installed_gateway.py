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
    "gateway_tls.py",
    "gateway_joint_ipc.py",
    "gateway_tls_receipt.py",
    "gateway_native_runtime.py",
    "gateway_native_receipt.py",
    "gateway_native_requests.py",
    "gateway_native_account.py",
    "gateway_read_sequence.py",
    "ledger_gateway.py",
    "selftest.py",
    "portfolio_rate_evidence.py",
    "portfolio_tls_provenance.py",
    "portfolio_egress_ledger.py",
)
PROFILE = "portfolio.installed_gateway_fixture.v8"


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
    def __init__(self, authority, sources, collector, guards, *, trust_sha256=None, sequence=None):
        self.authority, self.sources, self.collector, self.guards = (
            authority,
            sources,
            collector,
            guards,
        )
        self.sequence = sequence
        self.trust_sha256 = trust_sha256
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
            **({"read_sequence": self.sequence.verify()} if self.sequence is not None else {}),
            "base_manifest_sha256": self.authority.manifest_sha256,
            "gateway_manifest_sha256": self.sources.manifest_sha256,
            "collector": self.collector.selected,
            "rules": rules,
            "route": json.loads(run(self.guards["IP"], "-j", "route", "get", "198.51.100.2")),
            "net": os.readlink("/proc/self/ns/net"),
            **({"tls_trust_sha256": self.trust_sha256} if self.trust_sha256 else {}),
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


def run_controller(*, tls=False, receipt=False, native=False, account=False, sequence=None):
    authority = installation()
    collector = ledger = lifecycle = gateway = runtime = None
    try:
        fixture_context(authority)
        sources = InstalledGatewaySources(authority)
        gateway_code = load(sources.source("ledger_gateway.py"))
        guards = load(sources.source("selftest.py"))
        module = gateway_code["load_ledger"](
            {name: sources.source(name).decode() for name in FILES}
        )
        account_code = load(sources.source("gateway_native_account.py")) if account else None
        if account:
            module = account_code["ledger_view"](module)
        rates = (
            account_code["rates_view"]()
            if account
            else sys.modules["apps.strategies_nautilus.portfolio_rate_evidence"]
        )
        trust = None
        if tls:
            fd = authority.open_file("/etc/trader/egress-gateway-fixture-ca.pem", 0o444)
            trust = os.pread(fd, 65537, 0)
            authority.verify()
        launcher = load(authority.source("collector_launcher.py"))
        receiver = load(sources.source("gateway_tls_receipt.py")) if receipt else None
        native_code = (
            account_code
            if account
            else load(sources.source("gateway_native_receipt.py"))
            if native
            else None
        )
        if native:
            runtime = load(sources.source("gateway_native_runtime.py"))["NativeRuntime"](authority)
        collector = (
            account_code["launch"](authority, sources, launcher, runtime)
            if account
            else receiver["launch"](authority, sources, launcher, runtime=runtime)
            if receipt
            else launcher["FixtureCollector"].from_installation(authority)
        )
        binding = InstalledBinding(
            authority,
            sources,
            collector,
            guards,
            trust_sha256=digest(trust) if trust is not None else None,
            sequence=sequence,
        )
        if sequence is not None:
            sequence.bind(binding.selected)
        # This path cannot be chosen by the caller, collector or report contents.
        ledger = module.AttemptLedger(
            STORAGE if sequence is None else sequence.storage,
            binding=binding,
            binding_sha256=binding.pin,
            profile=module.PROFILE,
        )
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
        send = gateway_code["marked_echo"]
        if tls:
            transport = load(sources.source("gateway_tls.py"))

            def completed(raw):
                # Close the kernel window before waiting for the consumer. The
                # attempt stays pending until the authenticated payload receipt.
                gateway._revoke()
                provenance = sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"]
                report = transport["replay"](
                    raw,
                    expected_sha256=digest(raw),
                    attempts=ledger.expected,
                    lifecycle=lifecycle.expected,
                    binding_sha256=binding.pin,
                    trust_sha256=digest(trust),
                    ledger_module=module,
                    gateway_module=gateway_code,
                    provenance=provenance,
                    rates=rates,
                )
                payload = receiver["payload_from_tls"](raw, report)

                def prepared():
                    print(json.dumps({"stage": "receipt_prepared"}), flush=True)
                    if sys.stdin.readline() != "continue\n":
                        raise ValueError("fixture_parent_release_required")

                return receiver["deliver"](
                    collector,
                    ledger,
                    lifecycle,
                    payload,
                    provenance,
                    on_prepared=prepared,
                    native_result=native_code["expected_result"](payload) if native else None,
                )

            def send():
                return transport["capture"](
                    ledger,
                    lifecycle,
                    trust,
                    sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
                    rates,
                    on_complete=completed if receipt else None,
                    on_headers=lambda: print(
                        json.dumps({"stage": "tls_headers_persisted"}), flush=True
                    ),
                )

        def authorize():
            nonlocal transport
            if account:
                requests = load(sources.source("gateway_native_requests.py"))
                contract = account_code["authorize"](collector, ledger, authority, requests)
                transport = account_code["transport_view"](transport, contract)
                return {"ok": True, "request_sha256": contract.request_pin}
            return receiver["authorize"](collector) if receipt else collector.observe()

        gateway = gateway_code["FixtureLedgerGateway"](
            ledger,
            lifecycle=lifecycle,
            authorize=authorize,
            grant=grant,
            send=send,
            revoke=revoke,
        )
        try:
            gateway.dispatch()
        except (OSError, ValueError, RuntimeError) as exc:
            outcome = {"status": "refused", "reason": type(exc).__name__}
        else:
            outcome = {
                "status": "fixture_receipt_succeeded"
                if receipt
                else "fixture_tls_succeeded"
                if tls
                else "fixture_echo_succeeded"
            }
        try:
            gateway.close()
        except (OSError, ValueError, RuntimeError) as exc:
            outcome = {"status": "refused", "reason": type(exc).__name__}
        outcome = {**outcome, "revoked": gateway.revoked, "network_admitted": False}
        print(
            json.dumps(outcome),
            flush=True,
        )
        return outcome
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
                receiver["close"](collector) if receipt else collector.close()
        if runtime is not None:
            runtime.close()
        authority.close()


def main():
    if (
        sys.argv[1:]
        not in (
            ["--fixture"],
            ["--tls-fixture"],
            ["--joint-ipc-fixture"],
            ["--tls-receipt-fixture"],
            ["--native-receipt-fixture"],
            ["--native-requests-fixture"],
            ["--signed-account-fixture"],
            ["--read-sequence-fixture"],
        )
        or not sys.flags.isolated
        or os.path.abspath(__file__) != CODE + "/installed_gateway.py"
    ):
        raise ValueError("fixed_installed_fixture_entry_required")
    if sys.argv[1:] in (["--joint-ipc-fixture"], ["--native-requests-fixture"]):
        # Bootstrap through the same held installation before executing the extension.
        authority = installation()
        try:
            fixture_context(authority)
            sources = InstalledGatewaySources(authority)
            extension = load(
                sources.source(
                    "gateway_native_requests.py"
                    if sys.argv[1:] == ["--native-requests-fixture"]
                    else "gateway_joint_ipc.py"
                )
            )
            extension["run_installed"](globals(), authority, sources)
        finally:
            authority.close()
    elif sys.argv[1:] == ["--read-sequence-fixture"]:
        authority = installation()
        try:
            fixture_context(authority)
            sources = InstalledGatewaySources(authority)
            code = load(sources.source("gateway_read_sequence.py"))
            code["run_installed"](globals(), authority, sources)
        finally:
            authority.close()
    else:
        run_controller(
            tls=sys.argv[1:]
            in (
                ["--tls-fixture"],
                ["--tls-receipt-fixture"],
                ["--native-receipt-fixture"],
                ["--signed-account-fixture"],
            ),
            receipt=sys.argv[1:]
            in (
                ["--tls-receipt-fixture"],
                ["--native-receipt-fixture"],
                ["--signed-account-fixture"],
            ),
            native=sys.argv[1:] in (["--native-receipt-fixture"], ["--signed-account-fixture"]),
            account=sys.argv[1:] == ["--signed-account-fixture"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
