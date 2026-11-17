"""Regression tests for the gaps found while porting Satela (L1, L2)."""

import pytest

pytest.importorskip("aiosqlite")

from ushka.orm.database import UshkaDB  # noqa: E402


async def _db(tmp_path, name="t"):
    db = UshkaDB(f"sqlite:///{tmp_path / (name + '.db')}")
    return db


async def test_execute_commits_writes(tmp_path):
    db = await _db(tmp_path)

    class Log(db.Model):
        __tablename__ = "l1_log"
        what = db.String(length=10)

    async with db.engine.begin() as conn:
        await conn.run_sync(db.metadata.create_all, tables=[Log.__table__])
    row = await Log.create(what="a")
    await db.execute("update l1_log set what = 'b'")
    assert (await Log.get(row.id)).what == "b"
    await db.execute(db.text("update l1_log set what = :w", w="c"))
    assert (await Log.get(row.id)).what == "c"
    result = await db.execute("select what from l1_log")
    assert result.scalars().all() == ["c"]
    await db.engine.dispose()


def test_datetime_tz_is_timestamptz_and_uuid_is_native_on_postgres():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    db = UshkaDB("sqlite:///x.db")

    class Audit(db.Model):
        __tablename__ = "l2_audit"
        id = db.UUID(primary_key=True)
        moment = db.DateTime(tz=True)
        naive = db.DateTime()

    ddl = str(CreateTable(Audit.__table__).compile(dialect=postgresql.dialect()))
    assert "id UUID" in ddl
    assert "moment TIMESTAMP WITH TIME ZONE" in ddl
    assert "naive TIMESTAMP WITHOUT TIME ZONE" in ddl


async def test_datetime_tz_accepts_aware_values(tmp_path):
    from datetime import datetime, timezone

    db = await _db(tmp_path, "tz")

    class AuditRT(db.Model):
        __tablename__ = "l2_audit_rt"
        when = db.DateTime(tz=True)

    async with db.engine.begin() as conn:
        await conn.run_sync(db.metadata.create_all, tables=[AuditRT.__table__])
    row = await AuditRT.create(when=datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc))
    assert (await AuditRT.get(row.id)).when.replace(tzinfo=None) == datetime(2026, 11, 17, 10, 0)
    await db.engine.dispose()
