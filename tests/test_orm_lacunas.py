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
