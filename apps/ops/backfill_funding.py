"""Idempotently download and checksum Binance USD-M monthly funding archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

from apps.strategies_freqtrade.research.multi_asset_rotation_signals import UNIVERSE

BINANCE_UM_MONTHLY_FUNDING_URL = (
    "https://data.binance.vision/data/futures/um/monthly/fundingRate"
)


@dataclass(frozen=True)
class FundingBackfillResult:
    symbol: str
    start_date: str
    end_date: str
    months: int
    archives: list[dict[str, str]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_monthly_funding(
    *,
    symbol: str,
    month: str,
    output_dir: Path,
) -> tuple[Path, str]:
    symbol = symbol.upper()
    if symbol not in UNIVERSE:
        raise ValueError(f"symbol must be in locked universe {UNIVERSE}")
    file_name = f"{symbol}-fundingRate-{month}.zip"
    url = f"{BINANCE_UM_MONTHLY_FUNDING_URL}/{symbol}/{file_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / file_name
    checksum_path = output_dir / f"{file_name}.CHECKSUM"
    if not archive.exists():
        urllib.request.urlretrieve(url, archive)  # noqa: S310 - public market data.
    if not checksum_path.exists():
        urllib.request.urlretrieve(  # noqa: S310 - public market data.
            f"{url}.CHECKSUM",
            checksum_path,
        )
    fields = checksum_path.read_text(encoding="utf-8").strip().split()
    if not fields or len(fields[0]) != 64:
        raise ValueError(f"invalid checksum file {checksum_path}")
    expected = fields[0].lower()
    actual = _sha256(archive)
    if actual != expected:
        raise ValueError(f"checksum mismatch for {archive}: {actual}!={expected}")
    return archive, actual


def run_funding_backfill(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
) -> FundingBackfillResult:
    try:
        start = Date.fromisoformat(start_date)
        end = Date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("start_date/end_date must be YYYY-MM-DD") from exc
    if end < start:
        raise ValueError("end_date is before start_date")
    if start.day != 1 or (end + timedelta(days=1)).day != 1:
        raise ValueError("funding range must cover complete calendar months")
    current = start
    archives = []
    while current <= end:
        path, sha256 = download_monthly_funding(
            symbol=symbol,
            month=current.strftime("%Y-%m"),
            output_dir=output_dir,
        )
        archives.append({"path": str(path), "sha256": sha256})
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return FundingBackfillResult(
        symbol=symbol.upper(),
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        months=len(archives),
        archives=archives,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=UNIVERSE, required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/binance/futures/um/monthly/fundingRate"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_funding_backfill(
            symbol=args.symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        raise SystemExit(f"funding backfill failed: {exc}") from exc
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
