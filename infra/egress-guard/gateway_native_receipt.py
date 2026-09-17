"""Native metadata consumer functions; native imports run only after UID/cap drop."""

from __future__ import annotations

import base64
import json
import os
import re

PROFILE = "portfolio.installed_native_receipt.v1"
VERSION = "1.226.0"


def expected_result(payload):
    value = json.loads(payload)
    response = base64.b64decode(value["response_b64"], validate=True)
    body = response.split(b"\r\n\r\n", 1)[1]
    metadata = json.loads(body)
    symbols = metadata.get("symbols")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 16:
        raise ValueError("native_fixture_metadata_required")
    assets, names = {}, set()
    for symbol in symbols:
        name = symbol["symbol"]
        if name in names:
            raise ValueError("native_duplicate_symbol")
        names.add(name)
        for key in ("baseAsset", "quoteAsset"):
            asset, precision = symbol[key], symbol[key + "Precision"]
            if (
                not isinstance(asset, str)
                or re.fullmatch("[A-Z0-9]{1,16}", asset) is None
                or type(precision) is not int
                or not 0 <= precision <= 255
                or (asset in assets and assets[asset] != precision)
            ):
                raise ValueError("native_metadata_precision")
            assets[asset] = precision
        if name != symbol["baseAsset"] + symbol["quoteAsset"]:
            raise ValueError("native_symbol_assets")
    return {
        "profile": PROFILE,
        "native_version": VERSION,
        "currencies": [{"code": k, "precision": v} for k, v in sorted(assets.items())],
        "tls_sha256": value["tls_sha256"],
        "header_receipt": value["header_receipt"],
        "body_receipt": value["body_receipt"],
        "qualified_for_execution": False,
    }


def prepare_native():
    if os.geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    from nautilus_trader.core import nautilus_pyo3

    if nautilus_pyo3.NAUTILUS_VERSION != VERSION:
        raise ValueError("native_version_changed")


def validate_native(payload):
    prepare_native()
    from nautilus_trader.core.nautilus_pyo3 import Currency, CurrencyType

    result = expected_result(payload)
    objects = [
        Currency(r["code"], r["precision"], 0, r["code"], CurrencyType.CRYPTO)
        for r in result["currencies"]
    ]
    if [{"code": c.code, "precision": c.precision} for c in objects] != result["currencies"]:
        raise ValueError("native_currency_mapping_changed")
    return result
