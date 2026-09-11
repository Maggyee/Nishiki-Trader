"""Capture bounded testnet account/fee/filter GET evidence with the existing key."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_testnet_capabilities import (
    TestnetCapabilityHttpClient,
    collect_capabilities,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    load_testnet_ed25519_credentials,
)
from apps.strategies_nautilus.portfolio_testnet_observation import account_balances
from apps.strategies_nautilus.portfolio_testnet_session import (
    TestnetOrderValidationHttpClient,
    session_contract,
    validate_order,
)
from apps.strategies_nautilus.portfolio_venue import _unique_object


async def run(args):
    credentials = load_testnet_ed25519_credentials(args.credentials)
    with args.selection.open("rb") as source:
        initial = source.read(8 * 1024 * 1024 + 1)
    clock = LiveClock()
    client_type = (
        TestnetOrderValidationHttpClient if args.validate_order else TestnetCapabilityHttpClient
    )
    http = client_type(
        clock,
        credentials.api_key,
        None,
        TESTNET_REST,
        ed25519_private_key=credentials.private_key_pem,
    )
    # Reserve the output before network access. Never overwrite an old capture.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        result = await collect_capabilities(
            http, initial, args.selection_sha256, clock.timestamp_ns
        )
        result["session_contract"] = session_contract()
        result["code_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        result["code_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"]))
        result["code_sha256"] = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__).relative_to(Path.cwd()),
                Path("apps/strategies_nautilus/portfolio_testnet_capabilities.py"),
                Path("apps/strategies_nautilus/portfolio_testnet_session.py"),
                Path("apps/strategies_nautilus/portfolio_venue.py"),
            )
        }
        raw = json.dumps(result, sort_keys=True, indent=2).encode() + b"\n"
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
        if args.validate_order:
            result["order_validation"] = await validate_order(http, result, clock.timestamp_ns)

            # A failed later read must not erase the validation receipt.
            def persist():
                raw = json.dumps(result, sort_keys=True, indent=2).encode() + b"\n"
                output.seek(0)
                output.write(raw)
                output.truncate()
                output.flush()
                os.fsync(output.fileno())
                return raw

            persist()
            after = []
            for path, params in (
                ("/api/v3/account", {"omitZeroBalances": "false"}),
                ("/api/v3/openOrders", {}),
            ):
                started = clock.timestamp_ns()
                status, body = await http.sign_request(
                    HttpMethod.GET, path, params | {"timestamp": str(started // 1_000_000)}
                )
                after.append(
                    {
                        "path": path,
                        "status": status,
                        "params": params,
                        "started_ns": started,
                        "received_ns": clock.timestamp_ns(),
                        "body": body.decode(),
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
                result["post_validation_reads"] = after
                persist()
            before = json.loads(result["captures"][-1]["body"], object_pairs_hook=_unique_object)
            after_account = json.loads(after[0]["body"], object_pairs_hook=_unique_object)
            after_orders = json.loads(after[1]["body"], object_pairs_hook=_unique_object)
            result["validation_summary"] = {
                key: value
                for key, value in result["order_validation"].items()
                if key not in {"body", "params"}
            } | {
                "post_validation_full_balances_unchanged": all(r["status"] == 200 for r in after)
                and account_balances(before, result["source"]["account_uid"])
                == account_balances(after_account, result["source"]["account_uid"]),
                "post_validation_open_orders_empty": after[1]["status"] == 200
                and after_orders == [],
            }
            raw = persist()
    parent = os.open(args.output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return {
        "status": "diagnostic_completed",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "review": result["review"],
        "validation": result.get("validation_summary"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--validate-order",
        action="store_true",
        help="Also POST fixed /api/v3/order/test; never submits to matching engine",
    )
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"status": "diagnostic_failed", "runtime_ready": False}))
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0  # Diagnostic completion is never an order permit.


if __name__ == "__main__":
    raise SystemExit(main())
