from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from apps.ops.install_shadow_collectors import render_crontab
from apps.ops.research_forward_archives import series_rows, verified_archive


def test_archive_checksum_cache_and_tamper(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url)
        return hashlib.sha256(b"archive").hexdigest().encode() if url.endswith(".CHECKSUM") else b"archive"
    assert verified_archive("https://fixture/a.zip", tmp_path, fetch=fetch) == b"archive"
    assert verified_archive("https://fixture/a.zip", tmp_path, fetch=fetch) == b"archive"
    assert len(calls) == 2
    next(tmp_path.glob("*.zip")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verified_archive("https://fixture/a.zip", tmp_path, fetch=fetch)


def test_current_month_uses_closed_daily_archive(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        timestamp = int(datetime(2025,11,1,tzinfo=UTC).timestamp()*1000)
        archive.writestr("bars.csv", f"{timestamp},1,2,1,2,3\n")
    raw = buffer.getvalue()
    urls = []
    def fetch(url):
        urls.append(url)
        return hashlib.sha256(raw).hexdigest().encode() if url.endswith(".CHECKSUM") else raw
    rows = series_rows("premiumIndexKlines", tmp_path, now=datetime(2025,11,2,tzinfo=UTC), fetch=fetch)
    assert rows == [{"date":"2025-11-01", "value":2.0}]
    assert all("/daily/" in url and "2025-11-01.zip" in url for url in urls)


def test_cron_replacement_preserves_other_jobs_and_cadence(tmp_path):
    versions = (8,16,18,22,34,36,40,42,46,48)
    cron = "0 0 * * * unrelated-command\n" + "\n".join(
        f"15 3 * * 1-5 cd {tmp_path} && python -m apps.ops.research_v{v}_shadow_daily" for v in versions)
    rendered = render_crontab(cron, tmp_path, tmp_path / "deployment", "a"*40)
    assert rendered.startswith("0 0 * * * unrelated-command\n")
    assert rendered.count("--expected-commit") == 10
    assert rendered.count("15 3 * * 1-5") == 10
    with pytest.raises(ValueError, match="exactly one"):
        render_crontab(cron + f"\n15 3 * * 1-5 cd {tmp_path} && python -m apps.ops.research_v8_shadow_daily", tmp_path, tmp_path, "a"*40)


def test_missing_monthly_day_requires_verified_daily_archive(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url)
        days = [14] if "/daily/" in url else [i for i in range(30) if i != 14]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            rows = []
            for i in days:
                ts = int((datetime(2025, 11, 1, tzinfo=UTC) + timedelta(days=i)).timestamp()*1000)
                rows.append(f"{ts},1,2,1,2,3")
            archive.writestr("bars.csv", "\n".join(rows))
        raw = buffer.getvalue()
        return hashlib.sha256(raw).hexdigest().encode() if url.endswith(".CHECKSUM") else raw
    rows = series_rows("premiumIndexKlines", tmp_path, now=datetime(2025,12,1,tzinfo=UTC), fetch=fetch)
    assert len(rows) == 30
    assert any("daily/" in url and "2025-11-15.zip.CHECKSUM" in url for url in calls)
