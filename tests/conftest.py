"""Offline tests by default; opt-in Postgres tests use disposable schemas."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def offline_network(request, monkeypatch):
    if request.node.get_closest_marker("network") or request.node.get_closest_marker("postgres"):
        return

    def denied(*args, **kwargs):
        raise RuntimeError("Network disabled in unit tests; inject a fixture or mark network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def pg_conn_info():
    """Never connect to the default trader DB, even if it is available."""
    dsn = os.environ.get("TRADER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set TRADER_TEST_POSTGRES_DSN to an explicitly provisioned *_test database")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    params = conninfo_to_dict(dsn)
    if not params.get("dbname", "").endswith("_test") or params.get("service"):
        pytest.fail("Postgres tests require an explicit *_test database and no service indirection")
    schema = "trader_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True, connect_timeout=3) as admin:
        actual_db = admin.execute("SELECT current_database()").fetchone()[0]
        if actual_db != params["dbname"]:
            pytest.fail("Resolved Postgres database differs from explicit test database")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            isolated_dsn = make_conninfo(dsn, options=f"-csearch_path={schema}")
            ddl = (Path(__file__).resolve().parents[1] / "infra/postgres/init.sql").read_text()
            table = ddl.split("CREATE TABLE IF NOT EXISTS signal_events (", 1)[1].split(");", 1)[0]
            with psycopg.connect(isolated_dsn, autocommit=True) as conn:
                conn.execute("CREATE TABLE signal_events (" + table + ");")
            yield SimpleNamespace(to_conninfo=lambda: isolated_dsn)
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
