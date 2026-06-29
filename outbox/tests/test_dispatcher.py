"""Outbox dispatcher tests (ADR-0019, J3.1-c).

Bootstraps the cross-repo contract (outbox table + `outbox_reader` role + grants)
on a throwaway Postgres — basic-infra has no telcoss migration, so the test sets
up the contract per ADR-0019. Proves: ordered at-least-once delivery + marking;
restart/self-scan recovery of un-NOTIFYed rows; table-absent tolerance; and the
`outbox_reader` least-privilege boundary.
"""
from __future__ import annotations

import asyncio
import json

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from basic_infra_outbox import OutboxDispatcher, RecordingSink

_CONTRACT_DDL = [
    "CREATE SCHEMA IF NOT EXISTS inventory",
    "DROP TABLE IF EXISTS inventory.outbox",
    "CREATE TABLE inventory.outbox ("
    " id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
    " event_type TEXT NOT NULL, payload JSONB NOT NULL,"
    " occurred_at TIMESTAMPTZ NOT NULL, processed_at TIMESTAMPTZ)",
    "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='outbox_reader') "
    "THEN CREATE ROLE outbox_reader LOGIN NOSUPERUSER PASSWORD 'outbox_reader'; END IF; END $$",
    "GRANT USAGE ON SCHEMA inventory TO outbox_reader",
    "GRANT SELECT ON inventory.outbox TO outbox_reader",
    "GRANT UPDATE (processed_at) ON inventory.outbox TO outbox_reader",
]


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgis/postgis:16-3.4") as container:
        yield container


def _kwargs(pg, user, password):
    return {
        "host": pg.get_container_host_ip(),
        "port": int(pg.get_exposed_port(5432)),
        "user": user,
        "password": password,
        "database": pg.dbname,
    }


def _reader_dsn(pg) -> str:
    k = _kwargs(pg, "outbox_reader", "outbox_reader")
    return f"postgresql://{k['user']}:{k['password']}@{k['host']}:{k['port']}/{k['database']}"


@pytest.fixture
async def admin(pg):
    conn = await asyncpg.connect(**_kwargs(pg, pg.username, pg.password))
    for stmt in _CONTRACT_DDL:
        await conn.execute(stmt)
    yield conn
    await conn.close()


async def _insert(conn, event_type: str, payload: dict) -> None:
    await conn.execute(
        "INSERT INTO inventory.outbox (event_type, payload, occurred_at) "
        "VALUES ($1, $2::jsonb, now())",
        event_type,
        json.dumps(payload),
    )


def _dispatcher(pg, sink, **kw) -> OutboxDispatcher:
    return OutboxDispatcher(
        dsn=_reader_dsn(pg),
        table="inventory.outbox",
        channel="telcoss_outbox",
        sink=sink,
        **kw,
    )


async def test_delivers_all_in_id_order_and_marks(pg, admin):
    for i in range(5):
        await _insert(admin, f"E{i}", {"n": i})
    sink = RecordingSink()
    reader = await asyncpg.connect(_reader_dsn(pg))
    try:
        n = await _dispatcher(pg, sink).deliver_backlog(reader)
    finally:
        await reader.close()
    assert n == 5
    assert [e.event_type for e in sink.events] == [f"E{i}" for i in range(5)]
    assert [e.id for e in sink.events] == sorted(e.id for e in sink.events)
    assert sink.events[0].payload == {"n": 0}
    unprocessed = await admin.fetchval(
        "SELECT count(*) FROM inventory.outbox WHERE processed_at IS NULL"
    )
    assert unprocessed == 0


async def test_restart_self_scan_recovers_un_notified_row(pg, admin):
    await _insert(admin, "First", {})
    sink = RecordingSink()
    reader = await asyncpg.connect(_reader_dsn(pg))
    try:
        d = _dispatcher(pg, sink)
        assert await d.deliver_backlog(reader) == 1
        # second pass: nothing left
        assert await d.deliver_backlog(reader) == 0
        # a row inserted with NO notify is still found by the next self-scan
        await _insert(admin, "Late", {})
        assert await d.deliver_backlog(reader) == 1
    finally:
        await reader.close()
    assert [e.event_type for e in sink.events] == ["First", "Late"]


async def test_table_absent_is_tolerated(pg, admin):
    await admin.execute("DROP TABLE inventory.outbox")
    reader = await asyncpg.connect(_reader_dsn(pg))
    try:
        assert await _dispatcher(pg, RecordingSink()).deliver_backlog(reader) == 0
    finally:
        await reader.close()


async def test_outbox_reader_least_privilege(pg, admin):
    await _insert(admin, "E", {"a": 1})
    reader = await asyncpg.connect(_reader_dsn(pg))
    try:
        rows = await reader.fetch("SELECT id FROM inventory.outbox")
        rid = rows[0]["id"]
        # processed_at update is allowed
        await reader.execute(
            "UPDATE inventory.outbox SET processed_at = now() WHERE id = $1", rid
        )
        # mutating any other column is denied (column-level grant)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await reader.execute(
                "UPDATE inventory.outbox SET payload = '{}'::jsonb WHERE id = $1", rid
            )
    finally:
        await reader.close()


async def test_run_loop_delivers_then_stops(pg, admin):
    for i in range(3):
        await _insert(admin, f"R{i}", {"n": i})
    sink = RecordingSink()
    d = _dispatcher(pg, sink, poll_interval=0.3)
    stop = asyncio.Event()
    task = asyncio.create_task(d.run(stop=stop))
    try:
        for _ in range(50):  # startup self-scan should drain the 3 rows
            if len(sink.events) >= 3:
                break
            await asyncio.sleep(0.1)
    finally:
        stop.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert [e.event_type for e in sink.events] == ["R0", "R1", "R2"]
