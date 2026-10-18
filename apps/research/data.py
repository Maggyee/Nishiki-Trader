"""Binance Vision archives for research protocols.

Files are fetched once, verified against the published ``.CHECKSUM`` and cached
under ``data/research/raw/``. ``manifest.json`` records every file's SHA256.
Nothing dated inside the sealed future blind (from 2026-09-01) is fetched.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

BASE_URL = "https://data.binance.vision/data"
DATA_ROOT = Path("data/research")
BLIND_START = date(2026, 9, 1)

# dataset -> (url directory template, file name template, period kind)
DATASETS = {
    "spot_klines_1d": ("spot/monthly/klines/{symbol}/1d", "{symbol}-1d-{period}.zip", "monthly"),
    "um_klines_1d": (
        "futures/um/monthly/klines/{symbol}/1d",
        "{symbol}-1d-{period}.zip",
        "monthly",
    ),
    "um_metrics_daily": (
        "futures/um/daily/metrics/{symbol}",
        "{symbol}-metrics-{period}.zip",
        "daily",
    ),
}
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]


class BlindWindowError(ValueError):
    """Raised when a request reaches into the sealed future blind."""


def periods(kind: str, start: str, end: str) -> list[str]:
    """Monthly ``YYYY-MM`` or daily ``YYYY-MM-DD`` periods, inclusive."""
    if kind == "monthly":
        months = pd.period_range(start, end, freq="M")
        last_day = months[-1].end_time.date()
        result = [str(month) for month in months]
    else:
        days = pd.date_range(start, end, freq="D")
        last_day = days[-1].date()
        result = [day.strftime("%Y-%m-%d") for day in days]
    if last_day >= BLIND_START:
        raise BlindWindowError(f"{end} reaches the sealed blind starting {BLIND_START}")
    return result


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - public archive
        return response.read()


def fetch(
    dataset: str,
    symbol: str,
    start: str,
    end: str,
    *,
    root: Path = DATA_ROOT,
    get: Callable[[str], bytes] = _http_get,
    workers: int = 8,
) -> dict[str, str | None]:
    """Fetch and verify one dataset; return {relative path: sha256 or None if missing}."""
    directory, name_template, kind = DATASETS[dataset]
    url_dir = directory.format(symbol=symbol)

    def one(period: str) -> tuple[str, str | None]:
        name = name_template.format(symbol=symbol, period=period)
        relative = f"raw/{url_dir}/{name}"
        target = root / relative
        if target.exists():
            return relative, hashlib.sha256(target.read_bytes()).hexdigest()
        url = f"{BASE_URL}/{url_dir}/{name}"
        try:
            payload = get(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and kind == "daily":
                return relative, None  # daily archives have occasional gaps
            raise
        expected = get(f"{url}.CHECKSUM").decode().split()[0]
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise ValueError(f"checksum mismatch for {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".part")
        tmp.write_bytes(payload)
        tmp.replace(target)
        return relative, actual

    with ThreadPoolExecutor(max_workers=workers) as pool:
        entries = dict(pool.map(one, periods(kind, start, end)))
    _update_manifest(root, entries)
    return entries


def _update_manifest(root: Path, entries: dict[str, str | None]) -> None:
    path = root / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    manifest.update(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n")


def _read_zip_csv(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        name = sorted(n for n in archive.namelist() if n.endswith(".csv"))[0]
        return pd.read_csv(io.BytesIO(archive.read(name)), header=None, dtype=str)


def parse_klines(raw: pd.DataFrame) -> pd.DataFrame:
    """Binance kline CSV (with or without header) -> daily frame on a UTC index."""
    frame = raw.iloc[:, : len(KLINE_COLUMNS)].copy()
    frame.columns = KLINE_COLUMNS
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame[frame["open_time"].notna()]
    # Spot archives switched from milliseconds to microseconds on 2025-01-01.
    unit_us = frame["open_time"] >= 1e15
    stamps = pd.to_datetime(
        frame["open_time"].where(~unit_us, frame["open_time"] // 1000), unit="ms"
    )
    frame.index = pd.DatetimeIndex(stamps, tz="UTC").floor("D")
    columns = [c for c in KLINE_COLUMNS if c not in ("open_time", "close_time", "ignore")]
    return frame[columns].astype(float)


def parse_metrics(raw: pd.DataFrame) -> pd.DataFrame:
    """Binance 5-minute metrics CSV -> last open-interest row per UTC day."""
    frame = raw.copy()
    frame.columns = frame.iloc[0]
    frame = frame.iloc[1:]
    stamps = pd.DatetimeIndex(pd.to_datetime(frame["create_time"]), tz="UTC")
    out = pd.DataFrame(
        {
            "open_interest": frame["sum_open_interest"].astype(float).to_numpy(),
            "open_interest_value": frame["sum_open_interest_value"].astype(float).to_numpy(),
        },
        index=stamps,
    ).sort_index()
    return out.groupby(out.index.floor("D")).last()


def load(dataset: str, symbol: str, *, root: Path = DATA_ROOT) -> pd.DataFrame:
    """All cached files of one dataset/symbol as one sorted, de-duplicated frame."""
    directory, _, _ = DATASETS[dataset]
    files = sorted((root / "raw" / directory.format(symbol=symbol)).glob("*.zip"))
    if not files:
        raise FileNotFoundError(f"no cached {dataset} files for {symbol}; run fetch first")
    parse = parse_metrics if dataset == "um_metrics_daily" else parse_klines
    frame = pd.concat([parse(_read_zip_csv(path)) for path in files])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.index.max().date() >= BLIND_START:
        raise BlindWindowError(f"cached {dataset} {symbol} reaches the sealed blind")
    return frame


def load_frames(
    datasets: Iterable[str], symbols: Iterable[str], *, root: Path = DATA_ROOT
) -> dict[str, dict[str, pd.DataFrame]]:
    symbols = list(symbols)
    return {ds: {s: load(ds, s, root=root) for s in symbols} for ds in datasets}
