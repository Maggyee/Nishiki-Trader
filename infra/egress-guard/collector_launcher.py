"""Bounded rootless launcher/IPC acceptance only; never install a host helper.

The fixed child observes its control channel. It has no venue/network operation.
"""

from __future__ import annotations

import array
import hashlib
import json
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
from contextlib import suppress
from pathlib import Path

ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
PYTHON = "/usr/bin/python3"
PACKET_LIMIT = 1024
CREDENTIALS = struct.Struct("3i")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class ControlChannel:
    """Private SOCK_SEQPACKET endpoint; credentials come from each kernel message."""

    def __init__(self, connection, peer, *, timeout=2):
        self.connection, self.peer = connection, peer
        self.failed = False
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        connection.settimeout(timeout)

    def send(self, operation, sequence):
        if self.failed:
            raise RuntimeError("channel_terminal")
        try:
            raw = canonical({"v": 1, "op": operation, "seq": sequence})
            if len(raw) > PACKET_LIMIT or self.connection.send(raw) != len(raw):
                raise RuntimeError("channel_short_send")
        except BaseException:
            self.close()
            raise

    def receive(self, operations, sequence):
        if self.failed:
            raise RuntimeError("channel_terminal")
        try:
            raw, ancillary, flags, _ = self.connection.recvmsg(
                PACKET_LIMIT,
                socket.CMSG_SPACE(CREDENTIALS.size) + socket.CMSG_SPACE(16 * 4),
                socket.MSG_CMSG_CLOEXEC,
            )
            credentials = []
            unexpected = False
            for level, kind, value in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    # recvmsg installed these descriptors: close before rejecting them,
                    # including the delivered prefix of a truncated control message.
                    fds = array.array("i")
                    fds.frombytes(value[: len(value) - len(value) % fds.itemsize])
                    for fd in fds:
                        os.close(fd)
                    unexpected = True
                elif (
                    level == socket.SOL_SOCKET
                    and kind == socket.SCM_CREDENTIALS
                    and len(value) == CREDENTIALS.size
                ):
                    credentials.append(CREDENTIALS.unpack(value))
                else:
                    unexpected = True
            if (
                not raw
                or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
                or unexpected
                or credentials != [self.peer]
            ):
                raise RuntimeError("channel_credentials_or_frame")
            message = json.loads(raw)
            if (
                not isinstance(message, dict)
                or set(message) != {"v", "op", "seq"}
                or type(message["v"]) is not int
                or message["v"] != 1
                or type(message["seq"]) is not int
                or message["seq"] != sequence
                or message["op"] not in operations
                or raw != canonical(message)
            ):
                raise RuntimeError("channel_protocol")
            return message["op"]
        except BaseException:
            self.close()
            raise

    def close(self):
        self.failed = True
        self.connection.close()


def child_loop(fd, parent):
    """Fixed finite protocol: ready, at most one observation, then close."""
    channel = ControlChannel(socket.socket(fileno=fd), parent)
    try:
        channel.send("ready", 0)
        operation = channel.receive({"observe", "close"}, 1)
        if operation == "observe":
            channel.send("observed", 1)
            channel.receive({"close"}, 2)
            channel.send("closed", 2)
        else:
            channel.send("closed", 1)
    finally:
        channel.close()


class FixtureCollector:
    """Launch one fixed capability-dropped child in a fresh network namespace.

    Internal fixture API; source/identity_reader are trusted harness inputs, never
    remote request parameters. The public CLI accepts no arguments or code inputs.
    """

    def __init__(self, source, identity_reader):
        self.owner_pid = os.getpid()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.used = self.closed = False
        self.process = self.pidfd = self.channel = None
        self.identity_reader = identity_reader
        self.source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        # Enable before either process can queue its first message.
        for connection in (parent, child):
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        try:
            script = (
                f"scope={{'__name__':'fixture_collector'}}\nexec(compile({source!r},'<collector>','exec'),scope)\n"
                f"scope['child_loop']({child.fileno()}, {(os.getpid(), os.getuid(), os.getgid())!r})\n"
            )
            self.process = subprocess.Popen(
                [
                    "/usr/bin/unshare",
                    "--net",
                    "/usr/bin/setpriv",
                    "--bounding-set=-all",
                    "--inh-caps=-all",
                    "--ambient-caps=-all",
                    "--no-new-privs",
                    PYTHON,
                    "-I",
                    "-c",
                    script,
                ],
                pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=ENV,
                cwd="/",
            )
            self.pidfd = os.pidfd_open(self.process.pid)
            self.channel = ControlChannel(parent, (self.process.pid, os.getuid(), os.getgid()))
            child.close()
            self.channel.receive({"ready"}, 0)
            self.selected = self.binding()
            observed = self.selected["process"]
            # This rootless fixture maps the outer user to namespace UID 0. It
            # verifies capability removal, not a production dedicated nonroot UID.
            if (
                any(observed["capabilities"].values())
                or observed["no_new_privileges"] != 1
                or observed["namespaces"]["net"] == os.readlink("/proc/self/ns/net")
            ):
                raise RuntimeError("collector_isolation_missing")
            self.verify()
        except BaseException:
            parent.close()
            self.cleanup()
            raise
        finally:
            child.close()

    def check_owner(self):
        if os.getpid() != self.owner_pid:
            raise RuntimeError("launcher_foreign_owner")

    def binding(self):
        self.check_owner()
        return {
            "launcher_source_sha256": self.source_sha256,
            "process": self.identity_reader(self.process.pid),
        }

    def verify(self):
        self.check_owner()
        if self.closed or self.pidfd is None or select.select([self.pidfd], [], [], 0)[0]:
            raise RuntimeError("collector_exited_or_closed")
        if self.binding() != self.selected:
            raise RuntimeError("collector_identity_changed")

    def observe(self):
        self.check_owner()
        with self.lock:
            if self.stop.is_set() or self.closed or self.used:
                raise RuntimeError("collector_consumed_or_stopped")
            self.used = True  # Uncertain IPC completion never permits a resend.
            try:
                self.verify()
                self.channel.send("observe", 1)
                self.channel.receive({"observed"}, 1)
                self.verify()
                return {"ok": True}
            except BaseException:
                self.stop.set()
                self.cleanup()
                raise

    def cleanup(self):
        self.check_owner()
        if self.channel is not None:
            self.channel.close()
        try:
            if self.process is not None:
                if self.pidfd is not None:
                    with suppress(ProcessLookupError):
                        signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                else:
                    # Still our unreaped child if pidfd_open itself failed.
                    self.process.kill()
                self.process.wait(timeout=2)
        finally:
            if self.pidfd is not None:
                os.close(self.pidfd)
                self.pidfd = None
            self.closed = True

    def close(self):
        self.check_owner()
        self.stop.set()
        with self.lock:
            if self.closed:
                return
            try:
                self.verify()
                sequence = 2 if self.used else 1
                self.channel.send("close", sequence)
                self.channel.receive({"closed"}, sequence)
                self.process.wait(timeout=1)
            finally:
                self.cleanup()


def load_source(source):
    scope = {"__name__": "fixture_dependency"}
    exec(compile(source, "<fixture-dependency>", "exec"), scope)
    return scope


def worker(payload):
    def expired(_signal, _frame):
        raise TimeoutError("launcher_fixture_deadline")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(25)
    guards = load_source(payload["sources"]["selftest.py"])
    identities = load_source(payload["sources"]["inspect_binding.py"])
    guards["require_isolation"](payload["original"])
    guards["run"](
        "/usr/bin/mount", "-t", "tmpfs", "-o", "size=1m,nosuid,nodev,noexec", "tmpfs", "/tmp"
    )
    source = payload["sources"]["collector_launcher.py"]
    reader = identities["process_identity"]
    checks = []
    collector = FixtureCollector(source, reader)
    window = None
    try:
        checks.extend(
            [
                "kernel_ready_credentials_match_launched_pid",
                "collector_net_namespace_differs",
                "collector_all_capabilities_zero",
                "collector_no_new_privileges",
            ]
        )
        # A socketpair's cached peer credentials identify its creator, not the
        # post-exec sender. Acceptance deliberately relies on per-message creds.
        cached = CREDENTIALS.unpack(
            collector.channel.connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, CREDENTIALS.size
            )
        )
        if cached[0] != os.getpid() or cached[0] == collector.process.pid:
            raise RuntimeError("socketpair_peercred_assumption_changed")
        checks.append("cached_socketpair_peercred_is_not_child_authentication")
        storage = Path("/tmp/collector-scope")
        storage.mkdir(mode=0o700)
        guards["run"](guards["NFT"], "-f", "-", text=guards["WINDOW_RULES"])

        def window_binding():
            rules = guards["stable_rules"](
                json.loads(
                    guards["run"](guards["NFT"], "-j", "list", "table", "inet", "fixture_window")
                )
            )
            for row in rules["nftables"]:
                if row.get("set", {}).get("name") in {"permits", "blackout"}:
                    row["set"].pop("elem", None)
            return {"collector": collector.binding(), "rules": rules}

        window = guards["PersistentFixtureMaintenanceWindow"](
            storage, selected=window_binding(), observe=window_binding
        )
        collector.verify()
        window.activate()
        checks.append("authenticated_child_bound_to_durable_kernel_window_activation")

        def release():
            try:
                window.revoke()
            finally:
                collector.close()

        class Actor:
            def request(self, _request):
                rows = [json.loads(line) for line in guard.path.read_bytes().splitlines()]
                if rows[-1]["kind"] != "prepared":
                    raise RuntimeError("IPC preceded durable preparation")
                return collector.observe()

        class Once(guards["PersistentFixtureGuard"]):
            MAX_ATTEMPTS = 1

        guard = Once(
            storage,
            selected=collector.selected,
            observe=collector.binding,
            actor=Actor(),
            revoke=release,
        )
        try:
            guard.dispatch()
            checks.append("durable_preparation_before_authenticated_observation")
        finally:
            guard.close()
        window.close()
        if not window.revoked:
            raise RuntimeError("window_cleanup_missing")
        checks.append("kernel_window_revoked_before_collector_teardown_completes")
        activation_raw = window.journal.path.read_bytes()
        activation = guards["review_window_activation"](
            activation_raw,
            selected=window.selected,
            expected_sha256=hashlib.sha256(activation_raw).hexdigest(),
        )
        if (
            not activation["kernel_activation_return_recorded"]
            or not activation["cleanup_recorded"]
        ):
            raise RuntimeError("activation_replay_missing")
        checks.append("separate_kernel_and_ipc_journals_retain_distinct_attempts")
        if not collector.closed or collector.process.returncode is None:
            raise RuntimeError("collector_was_not_reaped")
        checks.append("terminal_close_reaps_child_and_closes_pidfd")
        raw = guard.path.read_bytes()
        replay = guards["review_fixture_journal"](
            raw, selected=collector.selected, expected_sha256=hashlib.sha256(raw).hexdigest()
        )
        if (
            replay["recorded_preparations"] != 1
            or not replay["revocation_recorded"]
            or replay["restart_allowed"]
        ):
            raise RuntimeError("launcher_journal_replay_failed")
        checks.append("terminal_journal_replays_without_restart_authority")
        try:
            Once(storage, selected={}, observe=lambda: {}, actor=Actor(), revoke=lambda: None)
        except FileExistsError:
            checks.append("consumed_scope_cannot_redispatch_via_journal")
        else:
            raise RuntimeError("scope_reopened")
    finally:
        try:
            if window is not None:
                window.close()
        finally:
            collector.close()
    guards["run"](guards["NFT"], "delete", "table", "inet", "fixture_window")

    exited = FixtureCollector(source, reader)
    try:
        signal.pidfd_send_signal(exited.pidfd, signal.SIGKILL)
        if not select.select([exited.pidfd], [], [], 2)[0]:
            raise RuntimeError("pidfd_exit_not_observed")
        try:
            exited.observe()
        except RuntimeError:
            checks.append("pidfd_death_refuses_observation_without_resend")
        else:
            raise RuntimeError("dead_collector_accepted")
    finally:
        exited.close()
    # The trusted helper disappears without shutdown. Its private endpoint closes;
    # the fixed collector must exit on EOF (or its bounded receive timeout).
    read_fd, write_fd = os.pipe()
    owner = os.fork()
    if owner == 0:
        os.close(read_fd)
        orphan = FixtureCollector(source, reader)
        os.write(write_fd, str(orphan.process.pid).encode())
        os._exit(0)
    os.close(write_fd)
    with os.fdopen(read_fd) as pipe:
        orphan_pid = int(pipe.read())
    _, owner_status = os.waitpid(owner, 0)
    if owner_status != 0:
        raise RuntimeError("helper_crash_setup_failed")
    orphan_fd = os.pidfd_open(orphan_pid)
    try:
        if not select.select([orphan_fd], [], [], 3)[0]:
            signal.pidfd_send_signal(orphan_fd, signal.SIGKILL)
            raise RuntimeError("collector_survived_helper_channel_loss")
        os.waitpid(orphan_pid, 0)  # Adopted by this disposable namespace's PID 1.
        checks.append("helper_death_closes_channel_and_collector_exits")
    finally:
        os.close(orphan_fd)
    return {
        "status": "passed",
        "checks": checks,
        "source_sha256": {
            name: hashlib.sha256(value.encode()).hexdigest()
            for name, value in payload["sources"].items()
        },
        "host_firewall_modified": False,
        "external_requests": 0,
        "production_helper_installed": False,
        "dedicated_uid_qualified": False,
        "capture_admitted": False,
        "gateway_coverage_qualified": False,
    }


def main():
    if len(sys.argv) != 1 or os.geteuid() == 0:
        print("Run as an ordinary user with no arguments.", file=sys.stderr)
        return 2
    directory = Path(__file__).parent
    sources = {
        name: (directory / name).read_text()
        for name in ("collector_launcher.py", "selftest.py", "inspect_binding.py")
    }
    original = {
        name: os.readlink("/proc/self/ns/" + name) for name in ("user", "net", "mnt", "pid")
    }
    bootstrap = (
        "import json,sys\npayload=json.load(sys.stdin)\nscope={'__name__':'launcher_fixture'}\n"
        "exec(compile(payload['sources']['collector_launcher.py'],'<launcher>','exec'),scope)\n"
        "print(json.dumps(scope['worker'](payload),sort_keys=True))\n"
    )
    process = subprocess.Popen(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
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
        ],
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
            json.dumps({"sources": sources, "original": original}), timeout=30
        )
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if original != {name: os.readlink("/proc/self/ns/" + name) for name in original}:
        raise RuntimeError("caller_namespace_changed")
    if process.returncode:
        print(stderr.strip(), file=sys.stderr)
        return 1
    print(stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
