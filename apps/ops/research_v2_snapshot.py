"""Collect immutable, credential-free Research Protocol v2 qualification snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.raw_snapshot.v1"
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v2-data-sources.json")
_OPTION_NAME_RE = re.compile(r"^BTC-[0-9]{1,2}[A-Z]{3}[0-9]{2}-[0-9]+-(?:C|P)$")


@dataclass(frozen=True)
class RequestSpec:
    name: str
    url: str
    params: dict[str, str | int]

    @property
    def full_url(self) -> str:
        query = urllib.parse.urlencode(self.params)
        return f"{self.url}?{query}" if query else self.url


Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-protocol-v2"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def build_requests(
    kind: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RequestSpec]:
    if kind == "options":
        if start_date or end_date:
            raise ValueError("options current-surface snapshot does not accept dates")
        return [
            RequestSpec(
                "btc_option_book_summaries",
                "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
                {"currency": "BTC", "kind": "option"},
            )
        ]
    if kind == "basis":
        if start_date or end_date:
            raise ValueError("basis current snapshot does not accept dates")
        base = "https://dapi.binance.com/futures/data/basis"
        return [
            RequestSpec(
                "current_quarter_basis",
                base,
                {"pair": "BTCUSD", "contractType": "CURRENT_QUARTER", "period": "1d", "limit": 1},
            ),
            RequestSpec(
                "next_quarter_basis",
                base,
                {"pair": "BTCUSD", "contractType": "NEXT_QUARTER", "period": "1d", "limit": 1},
            ),
            RequestSpec(
                "coin_m_exchange_info",
                "https://dapi.binance.com/dapi/v1/exchangeInfo",
                {},
            ),
        ]
    if kind == "stablecoin":
        if not start_date or not end_date:
            raise ValueError("stablecoin snapshot requires --start-date and --end-date")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start < date(2026, 7, 1) or end > date(2026, 7, 31) or end < start:
            raise ValueError("stablecoin qualification dates must stay within July 2026")
        return [
            RequestSpec(
                "stablecoin_asset_metrics",
                "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
                {
                    "assets": "usdt,usdc",
                    "metrics": "SplyCur,TxTfrValUSD",
                    "frequency": "1d",
                    "start_time": start_date,
                    "end_time": end_date,
                    "page_size": 10_000,
                },
            )
        ]
    raise ValueError(f"unsupported snapshot kind {kind!r}")


def _finite_positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{field} must be finite and positive")
    return number


def _validate_options(payloads: dict[str, Any]) -> dict[str, Any]:
    payload = payloads["btc_option_book_summaries"]
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise ValueError("Deribit response must be JSON-RPC 2.0")
    rows = payload.get("result")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Deribit option result must be a non-empty list")
    expiries: set[str] = set()
    liquid = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Deribit option rows must be objects")
        name = str(row.get("instrument_name", ""))
        if not _OPTION_NAME_RE.fullmatch(name):
            raise ValueError(f"unexpected BTC option instrument {name!r}")
        if row.get("base_currency") != "BTC":
            raise ValueError(f"option {name} has wrong base_currency")
        _finite_positive(row.get("creation_timestamp"), f"{name}.creation_timestamp")
        _finite_positive(row.get("mark_price"), f"{name}.mark_price")
        _finite_positive(row.get("mark_iv"), f"{name}.mark_iv")
        _finite_positive(row.get("underlying_price"), f"{name}.underlying_price")
        if row.get("underlying_index") in (None, ""):
            raise ValueError(f"{name}.underlying_index is missing")
        if row.get("bid_price") is not None and row.get("ask_price") is not None:
            liquid += 1
        expiries.add(name.split("-")[1])
    return {"row_count": len(rows), "expiry_count": len(expiries), "two_sided_count": liquid}


def _validate_basis(payloads: dict[str, Any], *, retrieved_at: datetime) -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    for name, contract_type in (
        ("current_quarter_basis", "CURRENT_QUARTER"),
        ("next_quarter_basis", "NEXT_QUARTER"),
    ):
        rows = payloads[name]
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError(f"{name} must contain exactly one row")
        row = rows[0]
        if row.get("pair") != "BTCUSD" or row.get("contractType") != contract_type:
            raise ValueError(f"{name} pair or contract type drifted")
        for field in ("indexPrice", "futuresPrice"):
            _finite_positive(row.get(field), f"{name}.{field}")
        annualized = float(row.get("annualizedBasisRate"))
        if not math.isfinite(annualized):
            raise ValueError(f"{name}.annualizedBasisRate must be finite")
        _finite_positive(row.get("timestamp"), f"{name}.timestamp")
        summaries[contract_type] = row

    exchange = payloads["coin_m_exchange_info"]
    symbols = exchange.get("symbols") if isinstance(exchange, dict) else None
    if not isinstance(symbols, list):
        raise ValueError("COIN-M exchangeInfo symbols must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    now_ms = int(retrieved_at.timestamp() * 1000)
    for row in symbols:
        if not isinstance(row, dict) or row.get("pair") != "BTCUSD":
            continue
        contract_type = row.get("contractType")
        if contract_type not in summaries or row.get("status") != "TRADING":
            continue
        delivery = int(_finite_positive(row.get("deliveryDate"), "deliveryDate"))
        if delivery <= now_ms:
            continue
        mapped[str(contract_type)] = row
    if set(mapped) != set(summaries):
        raise ValueError("exchangeInfo lacks trading BTCUSD current/next quarter mappings")
    if int(mapped["CURRENT_QUARTER"]["deliveryDate"]) >= int(
        mapped["NEXT_QUARTER"]["deliveryDate"]
    ):
        raise ValueError("quarterly delivery dates are not ordered")
    return {
        "contract_types": sorted(mapped),
        "symbols": {key: value["symbol"] for key, value in sorted(mapped.items())},
    }


def _validate_stablecoin(payloads: dict[str, Any]) -> dict[str, Any]:
    payload = payloads["stablecoin_asset_metrics"]
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Coin Metrics data must be a non-empty list")
    assets: set[str] = set()
    timestamps: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Coin Metrics rows must be objects")
        asset = str(row.get("asset", ""))
        if asset not in {"usdt", "usdc"}:
            raise ValueError(f"unexpected stablecoin asset {asset!r}")
        timestamp = str(row.get("time", ""))
        if not timestamp:
            raise ValueError("Coin Metrics row is missing time")
        key = (asset, timestamp)
        if key in timestamps:
            raise ValueError(f"duplicate Coin Metrics row {key}")
        timestamps.add(key)
        _finite_positive(row.get("SplyCur"), f"{asset}.{timestamp}.SplyCur")
        _finite_positive(row.get("TxTfrValUSD"), f"{asset}.{timestamp}.TxTfrValUSD")
        assets.add(asset)
    if assets != {"usdt", "usdc"}:
        raise ValueError("Coin Metrics response must include both usdt and usdc")
    return {"row_count": len(rows), "assets": sorted(assets)}


def collect_snapshot(
    kind: str,
    *,
    output_dir: Path,
    start_date: str | None = None,
    end_date: str | None = None,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    retrieved_at = now or datetime.now(UTC)
    if retrieved_at.tzinfo is None:
        raise ValueError("snapshot time must be timezone-aware")
    specs = build_requests(kind, start_date=start_date, end_date=end_date)
    requests: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}
    for spec in specs:
        raw = fetch(spec.full_url)
        if not raw:
            raise ValueError(f"{spec.name} returned an empty response")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{spec.name} returned invalid JSON") from exc
        payloads[spec.name] = payload
        requests.append(
            {
                "name": spec.name,
                "url": spec.full_url,
                "payload_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
                "payload": payload,
            }
        )
    if kind == "options":
        audit = _validate_options(payloads)
    elif kind == "basis":
        audit = _validate_basis(payloads, retrieved_at=retrieved_at)
    elif kind == "stablecoin":
        audit = _validate_stablecoin(payloads)
    else:  # guarded by build_requests
        raise AssertionError(kind)

    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "retrieved_at": retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "provider_contract": str(PROVIDER_CONTRACT),
        "requests": requests,
        "audit": audit,
        "boundaries": {
            "credentials_loaded": False,
            "pnl_computed": False,
            "signal_store_written": False,
            "nautilus_run": False,
            "source_policy_mutated": False,
        },
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"))
    snapshot_hash = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    envelope = {
        **core,
        "vintage_id": f"{kind}:{core['retrieved_at']}:{snapshot_hash[7:19]}",
        "snapshot_sha256": snapshot_hash,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = retrieved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{kind}-{stamp}-{snapshot_hash[7:19]}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path, envelope


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("options", "basis", "stablecoin"), required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v2/raw"))
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path, envelope = collect_snapshot(
        args.kind,
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(
        json.dumps(
            {
                "path": str(path),
                "kind": envelope["kind"],
                "vintage_id": envelope["vintage_id"],
                "snapshot_sha256": envelope["snapshot_sha256"],
                "audit": envelope["audit"],
                "boundaries": envelope["boundaries"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
