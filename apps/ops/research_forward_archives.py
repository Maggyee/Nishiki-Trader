"""Checksum-verified forward Binance daily data with completed-month caching.

Only the active shadow collectors use this adapter. Historical research
qualification modules and their frozen requests remain unchanged.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from uuid import uuid4

from apps.ops.research_shadow_runtime import atomic_json


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/forward-shadow-v2"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def verified_archive(url: str, cache: Path, *, fetch=_fetch) -> bytes:
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache / f"{key}.zip"
    receipt = cache / f"{key}.json"
    if path.exists() and receipt.exists():
        raw = path.read_bytes()
        proof = json.loads(receipt.read_text())
        if proof["url"] != url or proof["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("cached archive checksum mismatch")
        return raw
    raw = fetch(url)
    checksum = fetch(url + ".CHECKSUM").decode().split()[0]
    if checksum != hashlib.sha256(raw).hexdigest():
        raise ValueError("official archive checksum mismatch")
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("unreceipted archive differs from provider")
    else:
        with path.open("xb") as handle:
            handle.write(raw)
    atomic_json(receipt, {"url": url, "sha256": checksum})
    return raw


def _parse_archive(raw: bytes, first: date, end: date) -> dict:
    parsed = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [n for n in archive.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise ValueError("expected one CSV per official archive")
        for row in csv.reader(io.StringIO(archive.read(names[0]).decode())):
            if not row or row[0] == "open_time":
                continue
            timestamp = int(row[0])
            seconds = timestamp / (1e6 if timestamp >= 10**15 else 1e3)
            stamp = datetime.fromtimestamp(seconds, UTC)
            d = stamp.date()
            value = float(row[4])
            if stamp.time() != datetime.min.time() or not first <= d < end:
                raise ValueError("archive contains off-grid or out-of-window row")
            if not math.isfinite(value) or d.isoformat() in parsed:
                raise ValueError("invalid or duplicate archive observation")
            parsed[d.isoformat()] = value
    return parsed


def series_rows(kind: str, cache: Path, *, now: datetime, fetch=_fetch) -> list[dict]:
    # Warmup for unchanged signals beginning 2026-01-01, not a new research window.
    start = date(2025, 11, 1)
    current_month = now.date().replace(day=1)
    archives: list[tuple[str, date, date]] = []
    month = start
    while month < current_month:
        following = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        archives.append((f"monthly/{kind}/BTCUSDT/1d/BTCUSDT-1d-{month:%Y-%m}.zip", month, following))
        month = following
    day = current_month
    while day < now.date():
        archives.append((f"daily/{kind}/BTCUSDT/1d/BTCUSDT-1d-{day:%Y-%m-%d}.zip", day, day + timedelta(days=1)))
        day += timedelta(days=1)
    result = {}
    for suffix, first, end in archives:
        url = "https://data.binance.vision/data/futures/um/" + suffix
        try:
            raw = verified_archive(url, cache, fetch=fetch)
        except HTTPError as exc:
            # Yesterday's daily archive can still be publishing. No other missing
            # interval or network error is silently ignored.
            if exc.code == 404 and first == now.date() - timedelta(days=1):
                continue
            raise
        parsed = _parse_archive(raw, first, end)
        expected = {(first + timedelta(days=i)).isoformat() for i in range((end-first).days)}
        if suffix.startswith("monthly/"):
            for missing in sorted(expected - parsed.keys()):
                day = date.fromisoformat(missing)
                daily_url = ("https://data.binance.vision/data/futures/um/daily/" +
                             f"{kind}/BTCUSDT/1d/BTCUSDT-1d-{missing}.zip")
                body = verified_archive(daily_url, cache, fetch=fetch)
                parsed.update(_parse_archive(body, day, day + timedelta(days=1)))
        if set(parsed) != expected:
            raise ValueError(f"incomplete official archive: {suffix}; missing={sorted(expected - parsed.keys())}")
        result.update(parsed)
    return [{"date": d, "value": result[d]} for d in sorted(result)]


def snapshot_forward(kind: str, output_dir: Path, *, now: datetime | None = None, fetch=_fetch):
    observed = now or datetime.now(UTC)
    cache = output_dir / "archives"
    if kind == "premium":
        values = series_rows("premiumIndexKlines", cache, now=observed, fetch=fetch)
        rows = [{"date": r["date"], "premium_close": r["value"]} for r in values]
    elif kind == "basis":
        index = series_rows("indexPriceKlines", cache, now=observed, fetch=fetch)
        mark = series_rows("markPriceKlines", cache, now=observed, fetch=fetch)
        if [r["date"] for r in index] != [r["date"] for r in mark]:
            raise ValueError("mark/index date grid mismatch")
        rows = []
        for idx, mrk in zip(index, mark, strict=True):
            if idx["value"] <= 0 or mrk["value"] <= 0:
                raise ValueError("mark/index prices must be positive")
            rows.append({"date": idx["date"], "index_close": idx["value"],
                         "mark_close": mrk["value"], "basis": (mrk["value"]-idx["value"])/idx["value"]})
    else:
        raise ValueError("unknown forward series")
    envelope = {"schema_version": "research.forward_vision_snapshot.v2",
                "observed_at": observed.isoformat(), "kind": kind, "rows": rows}
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True, allow_nan=False).encode()).hexdigest()
    envelope.update(snapshot_sha256="sha256:"+digest, vintage_id=f"vision-{kind}:{observed.isoformat()}:{digest[:12]}")
    path = output_dir / f"{kind}-{observed:%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:8]}.json"
    atomic_json(path, envelope)
    return path, envelope, rows
