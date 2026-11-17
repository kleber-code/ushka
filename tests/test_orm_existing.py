"""`ushka db inspect` and `ushka db check-models`: adopting a schema another ORM made."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from ushka.cli import main
from ushka.orm import db
from ushka.orm.database import _Base
from ushka.orm.reflect import (
    compare,
    generate,
    kind_of,
    parse_default,
    reflect,
    table_from_model,
)


@pytest.fixture(autouse=True)
def clean_orm():
    """The ORM keeps one global registry: empty it around every test."""

    def wipe():
        db.metadata.clear()
        _Base.registry.dispose()
        db._engine = db._session_factory = None

    wipe()
    yield
    wipe()


def legacy_schema(url: str) -> None:
    """A schema as another ORM leaves it: Python-side defaults, FKs without ON DELETE."""
    meta = sa.MetaData()
    sa.Table(
        "customers", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(120), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean, nullable=False, default=True),  # Python-side only
        sa.Column("credits", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime, nullable=False, default=dt.datetime.now),
        sa.Column("updated_at", sa.DateTime, nullable=False, default=dt.datetime.now),
        sa.Column("notes", sa.Text),
    )
    sa.Table(
        "leads", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), server_default="new", nullable=False),
        sa.Column("hot", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("seen_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Index("ix_leads_status", "status"),
    )
    sa.Table(
        "documents", meta,
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("title", sa.String(50), nullable=False),
        sa.Column("data", sa.JSON),
    )
    sa.Table(
        "tags_links", meta,
        sa.Column("tag", sa.String(20), primary_key=True),
        sa.Column("doc_id", sa.Uuid, sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.UniqueConstraint("tag", "doc_id", name="uq_tag_doc"),
    )
    engine = sa.create_engine(url)
    meta.create_all(engine)
    engine.dispose()


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_schema(f"sqlite:///{path}")
    return f"sqlite:///{path}"


@pytest.fixture
def legacy_source(legacy_db, tmp_path):
    """The generated models, made outside the event loop (the CLI runs its own)."""
    return generated(legacy_db, tmp_path)


def generated(url: str, tmp_path, *extra: str) -> str:
    out = tmp_path / "models.py"
    main(["db", "inspect", "--url", url, "--write", str(out), "--force", *extra])
    return out.read_text()


def load(source: str) -> dict:
    namespace: dict = {}
    exec(compile(source, "models.py", "exec"), namespace)
    return namespace


# -- the generated code -----------------------------------------------------------


def test_inspect_writes_models_that_import(legacy_db, tmp_path):
    source = generated(legacy_db, tmp_path)
    ns = load(source)

    assert {"Customer", "Lead", "Document", "TagsLink"} <= set(ns)
    assert ns["Customer"].__tablename__ == "customers"
    assert "class Customer(db.Model):" in source  # integer `id`: db.Model supplies it
    assert "class Document(db.BaseModel):" in source  # not an integer `id`
    assert "class TagsLink(db.BaseModel):" in source  # composite key
    assert "ix_leads_status" in source
    assert "UniqueConstraint('tag', 'doc_id', name='uq_tag_doc')" in source


def test_generated_models_match_the_database(legacy_db, tmp_path):
    load(generated(legacy_db, tmp_path))
    mapped = [table_from_model(t) for t in db.metadata.tables.values()]
    reflected = asyncio.run(reflect(db.to_async_url(legacy_db)))
    assert compare(reflected, mapped) == []


def test_server_defaults_become_python_defaults(legacy_db, tmp_path):
    source = generated(legacy_db, tmp_path)
    assert "status = db.String(length=20, default='new')" in source
    assert "hot = db.Bool(default=True)" in source
    assert "seen_at = db.DateTime(auto_now=True)" in source


def test_python_side_defaults_are_warned_about_not_applied(legacy_db, tmp_path, capsys):
    source = generated(legacy_db, tmp_path)
    out = capsys.readouterr().out
    # `ativo` has no default in the database: the model must not invent one...
    assert "ativo = db.Bool(default=None)" in source
    assert "credits = db.Int()" in source
    # ...but it says what to do.
    assert "TODO(ushka db inspect): NOT NULL boolean without a server default" in source
    assert "Set default=False or default=True" in source
    assert "customers.ativo" in out
    assert "customers.credits" in out
    # timestamps
    assert "customers.created_at" in out and "auto_now=True" in source
    assert "customers.updated_at" in out
    assert "does not refresh it on UPDATE" in out


def test_foreign_keys_without_on_delete_are_listed(legacy_db, tmp_path, capsys):
    source = generated(legacy_db, tmp_path)
    out = capsys.readouterr().out
    assert "leads.customer_id" in out
    assert "no ON DELETE action" in out
    assert "customer_id = db.ForeignKey('customers.id', dtype=db.Int(), on_delete=None)" in source
    # existing actions are kept and not reported
    assert "owner_id = db.ForeignKey('customers.id', dtype=db.Int(), on_delete=db.SET_NULL, nullable=True)" in source
    assert "leads.owner_id" not in out
    assert "ondelete='CASCADE'" in source
    assert "tags_links.doc_id: foreign key" not in out


def test_stdout_is_pure_code_and_warnings_go_to_stderr(legacy_db, capsys):
    main(["db", "inspect", "--url", legacy_db])
    captured = capsys.readouterr()
    compile(captured.out, "models.py", "exec")
    assert "to review" in captured.err
    assert "customers.ativo" in captured.err


def test_table_filter_and_unknown_table(legacy_db, tmp_path, capsys):
    source = generated(legacy_db, tmp_path, "--table", "customers")
    assert "class Customer" in source and "class Lead" not in source
    with pytest.raises(SystemExit) as exc:
        main(["db", "inspect", "--url", legacy_db, "--table", "nope"])
    assert exc.value.code == 1
    assert "no such table: nope" in capsys.readouterr().err


def test_write_refuses_to_overwrite(legacy_db, tmp_path):
    out = tmp_path / "models.py"
    out.write_text("# mine\n")
    with pytest.raises(SystemExit):
        main(["db", "inspect", "--url", legacy_db, "--write", str(out)])
    assert out.read_text() == "# mine\n"
    main(["db", "inspect", "--url", legacy_db, "--write", str(out), "--force"])
    assert "class Customer" in out.read_text()


def test_inspect_uses_the_configured_database(legacy_db, workdir, monkeypatch, capsys):
    monkeypatch.setenv("USHKA_DATABASE_URL", legacy_db)
    main(["db", "inspect", "--table", "documents"])
    assert "class Document(db.BaseModel):" in capsys.readouterr().out


# -- they work -------------------------------------------------------------------------


async def test_create_and_delete_work_after_review(legacy_db, legacy_source):
    source = legacy_source
    # What a person does after reading the TODOs.
    source = source.replace("ativo = db.Bool(default=None)", "ativo = db.Bool(default=True)")
    source = source.replace("credits = db.Int()", "credits = db.Int(default=0)")
    source = source.replace(
        "created_at = db.DateTime()", "created_at = db.DateTime(auto_now=True)"
    ).replace("updated_at = db.DateTime()", "updated_at = db.DateTime(auto_now=True)")
    ns = load(source)
    Customer, Lead, Document = ns["Customer"], ns["Lead"], ns["Document"]

    db.configure(legacy_db)

    @event.listens_for(db.engine.sync_engine, "connect")
    def _fk_on(conn, _):  # SQLite ignores foreign keys unless asked
        conn.execute("PRAGMA foreign_keys=ON")

    customer = await Customer.create(name="Ana", email="ana@example.com")
    assert customer.ativo is True and customer.credits == 0 and customer.created_at

    lead = await Lead.create(customer_id=customer.id)
    assert lead.status == "new" and lead.hot is True and lead.seen_at

    await Document.create(id="d1", title="x", data={"a": 1})
    assert (await Document.get("d1")).data == {"a": 1}

    customer_id, lead_id = customer.id, lead.id
    # The real case: no ON DELETE in the database, so deleting the parent fails.
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await customer.delete()
    # The advice in the warning: children first, in one transaction.
    async with db.Session() as session:
        await session.delete(await session.get(Lead, lead_id))
        await session.delete(await session.get(Customer, customer_id))
        await session.commit()
    assert await Customer.all() == []
    await db.engine.dispose()


async def test_unreviewed_models_fail_loudly_not_silently(legacy_db, legacy_source):
    """Without the review, `ativo` is NOT NULL with no default: it errors, never writes False."""
    ns = load(legacy_source)
    db.configure(legacy_db)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await ns["Customer"].create(name="Ana", email="a@example.com")
    await db.engine.dispose()


# -- pieces ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql, kind, expected",
    [
        ("true", "bool", ("py", "True")),
        ("0", "bool", ("py", "False")),
        ("b'1'", "bool", ("py", "True")),
        ("(1)", "int", ("py", "1")),
        ("'abc'::character varying", "string", ("py", "'abc'")),
        ("'it''s'", "string", ("py", "\"it's\"")),
        ("new", "string", ("py", "'new'")),
        ("now()", "datetime", ("now", "")),
        ("CURRENT_TIMESTAMP", "datetime", ("now", "")),
        ("(datetime('now'))", "datetime", ("now", "")),
        ("CURRENT_DATE", "date", ("today", "")),
        ("gen_random_uuid()", "uuid", ("uuid", "")),
        ("nextval('t_id_seq'::regclass)", "int", ("serial", "")),
        ("'{}'::jsonb", "json", ("py", "dict")),
        ("1.5", "float", ("py", "1.5")),
        ("NULL", "string", ("none", "")),
    ],
)
def test_parse_default(sql, kind, expected):
    assert parse_default(sql, kind) == expected


def test_unmapped_default_is_kept_as_server_default(tmp_path):
    path = tmp_path / "d.db"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as c:
        c.execute(sa.text(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, d DATETIME DEFAULT '2020-01-01 00:00:00' NOT NULL)"
        ))
    engine.dispose()
    source = generated(f"sqlite:///{path}", tmp_path)
    assert "server_default=text(" in source
    load(source)


def test_awkward_column_names_are_kept(tmp_path):
    path = tmp_path / "n.db"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as c:
        c.execute(sa.text(
            'CREATE TABLE "items" (id INTEGER PRIMARY KEY, "metadata" TEXT, "class" TEXT, "my col" INTEGER)'
        ))
    engine.dispose()
    ns = load(generated(f"sqlite:///{path}", tmp_path))
    cols = {c.name for c in ns["Item"].__table__.columns}
    assert cols == {"id", "metadata", "class", "my col"}


def test_table_without_primary_key_is_reported(tmp_path):
    path = tmp_path / "p.db"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE logs (msg TEXT)"))
    engine.dispose()
    reflected = asyncio.run(reflect(f"sqlite+aiosqlite:///{path}"))
    _, findings = generate(reflected)
    assert [f.kind for f in findings] == ["no-primary-key"]


def test_sqlite_char32_is_flagged_as_a_possible_uuid(legacy_db, tmp_path, capsys):
    generated(legacy_db, tmp_path)
    assert "documents.id: CHAR(32)" in capsys.readouterr().out


async def test_uuid_and_composite_keys(tmp_path):
    """Types SQLite cannot reflect as UUID are checked straight from the model."""
    from ushka.orm.reflect import ColumnInfo, TableInfo

    table = TableInfo(
        "documents",
        columns=[
            ColumnInfo("id", sa.Uuid(), nullable=False, default="gen_random_uuid()"),
            ColumnInfo("owner", sa.Uuid(), nullable=True),
            ColumnInfo("title", sa.String(20), nullable=False),
        ],
        pk=["id"],
    )
    source, findings = generate([table])
    assert "id = db.UUID(primary_key=True)" in source
    assert "owner = db.UUID(nullable=True)" in source
    assert not any(f.kind == "not-null-no-default" for f in findings)
    ns = load(source)
    db.configure(f"sqlite:///{tmp_path / 'u.db'}")
    async with db.engine.begin() as conn:
        await conn.run_sync(db.metadata.create_all)
    doc = await ns["Document"].create(title="a")
    assert isinstance(doc.id, uuid.UUID)
    await db.engine.dispose()


def test_kind_of():
    assert kind_of(sa.Boolean()) == "bool"
    assert kind_of(sa.BigInteger()) == "bigint"
    assert kind_of(sa.Text()) == "text"
    assert kind_of(sa.Uuid()) == "uuid"


def test_foreign_key_helper_passes_on_delete_and_on_update():
    column = db.ForeignKey("users.id", on_delete=None, on_update="CASCADE")
    fk = next(iter(column.foreign_keys))
    assert fk.ondelete is None and fk.onupdate == "CASCADE"
    default = next(iter(db.ForeignKey("users.id").foreign_keys))
    assert default.ondelete == "CASCADE" and default.onupdate is None


def test_base_model_has_no_id_column():
    class Thing(db.BaseModel):
        __tablename__ = "things_base"
        code = sa.Column(sa.String(5), primary_key=True)

    class Other(db.Model):
        __tablename__ = "things_model"

    assert "id" not in Thing.__table__.columns
    assert Other.__table__.c.id.primary_key


# -- check-models ------------------------------------------------------------------------------


def test_check_models_agrees_with_the_generated_models(legacy_db, tmp_path, monkeypatch, capsys):
    (tmp_path / "models_ok.py").write_text(generated(legacy_db, tmp_path))
    monkeypatch.syspath_prepend(str(tmp_path))
    capsys.readouterr()
    main(["db", "check-models", "--url", legacy_db, "--models", "models_ok"])
    assert "match the database" in capsys.readouterr().out


def test_check_models_lists_divergences(legacy_db, tmp_path, monkeypatch, capsys):
    source = generated(legacy_db, tmp_path)
    source = source.replace("name = db.String(length=100)", "name = db.String(length=100, nullable=True)")
    source = source.replace("on_delete=None)", "on_delete=db.CASCADE)")
    source = source.replace("    notes = db.Text(nullable=True)\n", "    nickname = db.String()\n")
    (tmp_path / "models_bad.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        main(["db", "check-models", "--url", legacy_db, "--models", "models_bad"])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "customers.name: nullable is True in the model but False" in out
    assert "customers.nickname: in the model, missing in the database" in out
    assert "customers.notes: in the database, missing in the model" in out
    assert "ON DELETE is CASCADE in the model but NO ACTION in the database" in out
