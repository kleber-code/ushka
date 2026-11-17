"""ORM: transactions, automatic timestamps, mirrored tables, UUID keys, cycles."""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid
import warnings

import pytest
from sqlalchemy import Column, Integer, String, Table, update
from sqlalchemy.exc import InvalidRequestError

from ushka.orm import db, utcnow


@pytest.fixture
async def sqlite(tmp_path):
    """The shared `db` pointed at a throwaway SQLite file."""
    old = db._url
    db.configure(f"sqlite:///{tmp_path / 'orm.db'}")
    yield db
    await db.engine.dispose()
    db._url = old
    db._engine = db._session_factory = None


async def create(*models):
    async with db.engine.begin() as conn:
        await conn.run_sync(
            lambda c: db.metadata.create_all(c, tables=[m.__table__ for m in models])
        )


class Lead(db.Model):
    __tablename__ = "t_leads"
    name = db.String(length=50)
    created_at = db.DateTime(auto_now_add=True)
    updated_at = db.DateTime(auto_now=True)
    notes = db.Relationship("Note", back_populates="lead")


class Note(db.Model):
    __tablename__ = "t_notes"
    text = db.String(length=50)
    lead_id = db.ForeignKey("t_leads.id")
    lead = db.Relationship("Lead", back_populates="notes")


async def count(model):
    return len(await model.all())


# --- transactions -----------------------------------------------------------


async def test_commit_on_exit(sqlite):
    await create(Lead, Note)
    async with db.transaction():
        lead = await Lead.create(name="ann")
        await Note.create(text="hi", lead_id=lead.id)
        assert db.in_transaction
    assert not db.in_transaction
    assert await count(Lead) == 1 and await count(Note) == 1


async def test_rollback_on_exception_undoes_every_operation(sqlite):
    await create(Lead, Note)
    with pytest.raises(RuntimeError):
        async with db.atomic():
            lead = await Lead.create(name="ann")
            await Note.create(text="hi", lead_id=lead.id)
            await db.execute(
                db.text(
                    "INSERT INTO t_leads (name, created_at, updated_at) "
                    "VALUES ('x', '2020-01-01', '2020-01-01')"
                )
            )
            raise RuntimeError("boom")
    assert await count(Lead) == 0 and await count(Note) == 0


async def test_reads_see_uncommitted_writes_inside(sqlite):
    await create(Lead)
    async with db.transaction():
        lead = await Lead.create(name="ann")
        assert (await Lead.get(lead.id)).name == "ann"
        assert len(await Lead.filter(name="ann")) == 1
        await lead.delete()
        assert await count(Lead) == 0


async def test_outside_block_each_call_commits(sqlite):
    await create(Lead)
    await Lead.create(name="a")
    await Lead.create(name="b")
    assert await count(Lead) == 2


async def test_nested_savepoint_rolls_back_only_inner(sqlite):
    await create(Lead)
    async with db.transaction():
        await Lead.create(name="outer")
        with pytest.raises(ValueError):
            async with db.transaction():
                await Lead.create(name="inner")
                raise ValueError
        await Lead.create(name="after")
    assert sorted(x.name for x in await Lead.all()) == ["after", "outer"]


async def test_nested_inner_success_outer_failure_rolls_back_all(sqlite):
    await create(Lead)
    with pytest.raises(ValueError):
        async with db.transaction():
            async with db.transaction():
                await Lead.create(name="inner")
            raise ValueError
    assert await count(Lead) == 0


async def test_nested_without_savepoint_joins_outer(sqlite):
    await create(Lead)
    async with db.transaction():
        await Lead.create(name="outer")
        try:
            async with db.transaction(savepoint=False):
                await Lead.create(name="inner")
                raise ValueError
        except ValueError:
            pass
    # no savepoint: the inner work was not undone on its own
    assert await count(Lead) == 2


async def test_transactions_are_isolated_between_tasks(sqlite):
    await create(Lead)
    started, release = asyncio.Event(), asyncio.Event()
    seen = {}

    async def failing():
        with pytest.raises(RuntimeError):
            async with db.transaction():
                await Lead.create(name="doomed")
                started.set()
                await release.wait()
                raise RuntimeError

    async def other():
        await started.wait()
        seen["in_tx"] = db.in_transaction
        seen["rows"] = await count(Lead)  # its own session: no dirty read
        release.set()

    await asyncio.gather(failing(), other())
    assert seen == {"in_tx": False, "rows": 0}
    assert await count(Lead) == 0
    async with db.transaction():
        await Lead.create(name="kept")
    assert [x.name for x in await Lead.all()] == ["kept"]


async def test_child_task_does_not_share_the_session(sqlite):
    await create(Lead)
    seen = {}

    async def child():
        seen["in_tx"] = db.in_transaction
        seen["rows"] = await count(Lead)

    async with db.transaction():
        await Lead.create(name="parent")
        assert await count(Lead) == 1
        await asyncio.create_task(child())
    assert seen == {"in_tx": False, "rows": 0}
    assert await count(Lead) == 1


async def test_transaction_yields_the_session(sqlite):
    await create(Lead)
    async with db.transaction() as session:
        session.add(Lead(name="raw"))
    assert await count(Lead) == 1


# --- automatic timestamps ---------------------------------------------------


async def test_auto_now_add_and_auto_now_on_create(sqlite):
    await create(Lead)
    before = utcnow()
    lead = await Lead.create(name="a")
    assert lead.created_at.tzinfo is not None
    assert before - dt.timedelta(seconds=1) <= lead.created_at <= utcnow()
    assert lead.updated_at.utcoffset() == dt.timedelta(0)


async def test_auto_now_changes_on_save_but_not_auto_now_add(sqlite):
    await create(Lead)
    lead = await Lead.create(name="a")
    created, updated = lead.created_at, lead.updated_at
    await asyncio.sleep(0.01)
    lead.name = "b"
    await lead.save()
    assert lead.created_at == created
    assert lead.updated_at > updated


async def test_auto_now_in_bulk_update(sqlite):
    await create(Lead)
    lead = await Lead.create(name="a")
    await asyncio.sleep(0.01)
    async with db.transaction():
        await db.execute(update(Lead).where(Lead.id == lead.id).values(name="z"))
    fresh = await Lead.get(lead.id)
    assert fresh.name == "z" and fresh.updated_at > lead.updated_at
    assert fresh.created_at == lead.created_at


async def test_naive_timestamps_when_timezone_false(sqlite):
    class Naive(db.Model):
        __tablename__ = "t_naive"
        at = db.DateTime(auto_now_add=True, timezone=False)

    await create(Naive)
    row = await Naive.create()
    assert row.at.tzinfo is None


def test_plain_datetime_has_no_default():
    col = db.DateTime(nullable=True)
    assert col.default is None and col.onupdate is None


# --- mirrored tables --------------------------------------------------------


async def test_extend_existing(sqlite):
    Table(
        "t_legacy", db.metadata, Column("id", Integer, primary_key=True),
        Column("name", String(20)),
    )

    class Legacy(db.BaseModel):
        __tablename__ = "t_legacy"

        __extend_existing__ = True

        id = Column(Integer, primary_key=True)
        name = Column(String(20))

    await create(Legacy)
    row = await Legacy.create(name="x")
    assert row.id == 1


def test_duplicate_table_without_meta_still_fails():
    Table("t_dup", db.metadata, Column("id", Integer, primary_key=True))
    with pytest.raises(InvalidRequestError):

        class Dup(db.BaseModel):
            __tablename__ = "t_dup"
            id = Column(Integer, primary_key=True)


def test_extend_existing_merges_tuple_table_args():
    Table("t_legacy2", db.metadata, Column("id", Integer, primary_key=True))

    class Legacy2(db.BaseModel):
        __tablename__ = "t_legacy2"
        __table_args__ = (Column("extra", Integer), {"comment": "c"})

        __extend_existing__ = True

        id = Column(Integer, primary_key=True)

    assert Legacy2.__table__.comment == "c"
    assert "extra" in Legacy2.__table__.c


# --- UUID keys --------------------------------------------------------------


async def test_uuid_primary_key_replaces_default_id(sqlite):
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class Doc(db.Model):
            __tablename__ = "t_docs"
            id = db.UUID(primary_key=True, default=uuid.uuid4)
            title = db.String(length=20)

        await create(Doc)
    assert [c.name for c in Doc.__table__.primary_key] == ["id"]
    doc = await Doc.create(title="t")
    assert isinstance(doc.id, uuid.UUID)
    got = await Doc.get(doc.id)
    assert got.id == doc.id and isinstance(got.id, uuid.UUID)
    assert (await Doc.first(id=doc.id)).title == "t"
    assert doc.to_dict()["id"] == str(doc.id)


async def test_uuid_default_generated_without_explicit_default(sqlite):
    class Doc2(db.Model):
        __tablename__ = "t_docs2"
        id = db.UUID(primary_key=True)

    await create(Doc2)
    a, b = await Doc2.create(), await Doc2.create()
    assert a.id != b.id


async def test_base_model_without_default_id(sqlite):
    class Tag(db.BaseModel):
        __tablename__ = "t_tags"
        code = Column(String(10), primary_key=True)

    assert "id" not in Tag.__table__.c
    await create(Tag)
    assert (await Tag.create(code="a")).code == "a"


async def test_uuid_is_char32_on_sqlite(sqlite):
    class Doc3(db.Model):
        __tablename__ = "t_docs3"
        id = db.UUID(primary_key=True)

    await create(Doc3)
    doc = await Doc3.create()
    rows = (await db.execute(db.text("SELECT id FROM t_docs3"))).all()
    assert rows[0][0] == doc.id.hex and len(rows[0][0]) == 32


# --- cyclic foreign keys ----------------------------------------------------


def _cycle(prefix, use_alter):
    app = type(f"{prefix}App", (db.Model,), {
        "__tablename__": f"{prefix}_app",
        "release_id": db.ForeignKey(
            f"{prefix}_release.id", nullable=True, use_alter=use_alter
        ),
    })
    release = type(f"{prefix}Release", (db.Model,), {
        "__tablename__": f"{prefix}_release",
        "app_id": db.ForeignKey(f"{prefix}_app.id"),
    })
    return app, release


async def test_cycle_warns_without_use_alter(sqlite):
    App, Release = _cycle("cy1", False)
    await create(App, Release)
    with pytest.warns(Warning, match="sort tables"):
        async with db.engine.begin() as conn:
            await conn.run_sync(
                lambda c: db.metadata.drop_all(c, tables=[App.__table__, Release.__table__])
            )


async def test_cycle_with_use_alter_is_silent_and_works(sqlite):
    App, Release = _cycle("cy2", True)
    both = [App.__table__, Release.__table__]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await create(App, Release)
        async with db.engine.begin() as conn:
            await conn.run_sync(lambda c: db.metadata.drop_all(c, tables=both))
        await create(App, Release)
    app = await App.create()
    rel = await Release.create(app_id=app.id)
    app.release_id = rel.id
    await app.save()
    assert (await App.get(app.id)).release_id == rel.id
