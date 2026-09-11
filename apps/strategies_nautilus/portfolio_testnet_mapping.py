"""Detached full-account mapping from pinned testnet metadata; no runtime account."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from nautilus_trader.accounting.accounts.cash import CashAccount
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.enums import AccountType, CurrencyType
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.objects import AccountBalance, Currency, Money

from apps.strategies_nautilus.portfolio_stream import StreamError
from apps.strategies_nautilus.portfolio_testnet_observation import _name
from apps.strategies_nautilus.portfolio_venue import _decimal, _unique_object

ENDPOINT = "https://testnet.binance.vision/api/v3/exchangeInfo"


def map_observed_balances(raw, *, expected_sha256, balances, account_uid, observed_ns):
    """Isolate native currency registration in a fresh, bounded diagnostic process."""
    if not 0 < len(raw) <= 16 * 1024 * 1024:
        raise StreamError("bounded exchange metadata required")
    request = {
        "raw": raw.decode(),
        "expected_sha256": expected_sha256,
        "balances": {asset: [str(free), str(locked)] for asset, (free, locked) in balances.items()},
        "account_uid": account_uid,
        "observed_ns": observed_ns,
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "apps.strategies_nautilus.portfolio_testnet_mapping"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=30,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
        )
        if result.returncode:
            raise StreamError("isolated native account mapping rejected selected evidence")
        return json.loads(result.stdout, object_pairs_hook=_unique_object)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise StreamError("isolated native account mapping failed") from None


def _map_observed_balances(raw, *, expected_sha256, balances, account_uid, observed_ns):
    """Native numeric comparison only; listing precision is not execution qualification.

    Symbols need not be tradable. All appearances of an asset must agree on
    precision. Missing/conflicting definitions prevent whole-account creation.
    CashAccount may register currencies. This runs only inside the diagnostic
    child process; its registry is discarded when the process exits.
    """
    if not 0 < len(raw) <= 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise StreamError("selected testnet exchange metadata changed")
    wrapped = json.loads(raw, object_pairs_hook=_unique_object)
    if (
        wrapped["schema_version"] != "portfolio.testnet_exchange_info_observation.v1"
        or wrapped["endpoint"] != ENDPOINT
        or type(wrapped["started_ns"]) is not int
        or type(wrapped["received_ns"]) is not int
        or not 0 < wrapped["started_ns"] <= wrapped["received_ns"]
        or hashlib.sha256(wrapped["response_body"].encode()).hexdigest()
        != wrapped["response_sha256"]
        or type(observed_ns) is not int
        or observed_ns <= 0
    ):
        raise StreamError("invalid testnet exchange metadata observation")
    body = json.loads(wrapped["response_body"], object_pairs_hook=_unique_object)
    symbols = body["symbols"]
    if not isinstance(symbols, list) or not 0 < len(symbols) <= 10000:
        raise StreamError("bounded exchange symbol metadata required")
    precisions, seen = defaultdict(set), set()
    for symbol in symbols:
        name = _name(symbol["symbol"])
        if name in seen:
            raise StreamError("duplicate exchange symbol metadata")
        seen.add(name)
        for asset_field, precision_field in (
            ("baseAsset", "baseAssetPrecision"),
            ("quoteAsset", "quoteAssetPrecision"),
        ):
            asset, precision = _name(symbol[asset_field]), symbol[precision_field]
            if type(precision) is not int or not 0 <= precision <= 16:
                raise StreamError("invalid native asset precision")
            precisions[asset].add(precision)
    rows, native_balances = [], []
    for asset, (free, locked) in sorted(balances.items()):
        options = precisions[asset]
        if len(options) != 1:
            rows.append(
                {
                    "asset": asset,
                    "status": "missing_metadata" if not options else "conflicting_precision",
                }
            )
            continue
        precision = next(iter(options))
        try:
            # Explicit metadata-derived precision, never Currency.from_str's fallback.
            currency = Currency(asset, precision, 0, asset, CurrencyType.CRYPTO)
            total_money, locked_money, free_money = (
                Money(value, currency) for value in (free + locked, locked, free)
            )
            if tuple(m.as_decimal() for m in (free_money, locked_money, total_money)) != (
                free,
                locked,
                free + locked,
            ):
                status = "native_amount_rounding"
            else:
                native_balances.append(AccountBalance(total_money, locked_money, free_money))
                status = "exact_observed_amounts"
        except (ValueError, ArithmeticError):
            status = "native_amount_unrepresentable"
        rows.append({"asset": asset, "precision": precision, "status": status})
    equal = False
    if balances and len(native_balances) == len(balances):
        # A constructed diagnostic event, explicitly NOT a reported venue event.
        event = AccountState(
            account_id=AccountId(f"BINANCE-{account_uid}"),
            account_type=AccountType.CASH,
            base_currency=None,
            balances=native_balances,
            margins=[],
            reported=False,
            info={"diagnostic_observation_mapping": True},
            event_id=UUID4(),
            ts_event=observed_ns,
            ts_init=observed_ns,
        )
        account = CashAccount(event)
        normalized = {
            c.code: (b.free.as_decimal(), b.locked.as_decimal())
            for c, b in account.balances().items()
        }
        equal = normalized == balances
        if not equal:
            raise StreamError("detached native account differs from full observed balances")
    return {
        "metadata_sha256": expected_sha256,
        "metadata_received_ns": wrapped["received_ns"],
        "metadata_current_for_execution_verified": False,
        "assets": rows,
        "exact_assets": len(native_balances),
        "detached_native_account_balances_equal": equal,
        "native_mapping_qualified": False,
        "runtime_ready": False,
        "isolated_native_process": True,
    }


def _main():
    try:
        request = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
        if len(request) > 32 * 1024 * 1024:
            raise StreamError("bounded native mapping request required")
        request = json.loads(request, object_pairs_hook=_unique_object)
        request["raw"] = request["raw"].encode()
        request["balances"] = {
            asset: tuple(_decimal(value) for value in values)
            for asset, values in request["balances"].items()
        }
        print(json.dumps(_map_observed_balances(**request), sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "native_mapping_failed", "runtime_ready": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
