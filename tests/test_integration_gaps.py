"""Pieces merged from the Satela gaps working together: database sessions,
`Depends` interrupting with a redirect and flash, `db.execute` in and out of
`db.transaction()`, host routing behind a trusted proxy."""

from __future__ import annotations

import pytest

pytest.importorskip("aiosqlite")

from ushka import Depends, HTTPRedirect, HTTPResponse, Request, Response
from ushka.orm import db
from ushka.templating.flash import flash, get_flashed_messages
from ushka.testing import TestClient


@pytest.fixture(autouse=True)
def secret_key(monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", "k" * 40)


class Gap(db.Model):
    __tablename__ = "gap_rows"
    label = db.String(length=20)


async def _create_tables():
    async with db.engine.begin() as conn:
        await conn.run_sync(lambda c: db.metadata.create_all(c, tables=[Gap.__table__]))


@pytest.fixture
async def dbapp(workdir, make_app):
    (workdir / "ushka.toml").write_text(
        f'[session]\nstore = "database"\n[database]\nurl = "sqlite:///{workdir}/gap.db"\n'
    )
    app = make_app()
    old = db._url
    db.configure(f"sqlite:///{workdir}/gap.db")
    await _create_tables()
    yield app
    await db.engine.dispose()
    db._url = old
    db._engine = db._session_factory = None


async def test_depends_redirect_flash_session_and_db_writes(dbapp):
    app = dbapp

    async def login_required(request: Request):
        if not request.session.get("user"):
            request.session["next"] = request.path
            flash(request, "Please sign in")
            raise HTTPRedirect("/login")
        return request.session["user"]

    @app.get("/secret")
    async def secret(user=Depends(login_required)):
        return {"user": user}

    @app.get("/login")
    async def login(request: Request):
        return {"next": request.session.get("next"), "messages": get_flashed_messages(request)}

    @app.post("/write")
    async def write():
        row = await Gap.create(label="a")
        await db.execute("update gap_rows set label = 'b'")  # outside a transaction: commits
        got = (await Gap.get(row.id)).label
        try:
            async with db.transaction():
                await db.execute("update gap_rows set label = 'c'")
                raise RuntimeError("undo")
        except RuntimeError:
            pass
        return {"before": got, "after": (await Gap.get(row.id)).label}

    async with TestClient(app) as client:
        first = await client.get("/secret")
        assert first.status_code == 302 and first.headers["location"] == "/login"
        second = await client.get("/login")
        assert second.json() == {"next": "/secret", "messages": ["Please sign in"]}
        res = await client.post("/write")
        # the write outside survived; the one inside the rolled-back block did not
        assert res.json() == {"before": "b", "after": "b"}


async def test_db_execute_joins_the_transaction_and_commits_with_it(dbapp):
    row = await Gap.create(label="a")
    async with db.transaction():
        await db.execute("update gap_rows set label = 'x'")
        assert db.in_transaction
        # same session: the block sees its own write
        assert (await Gap.get(row.id)).label == "x"
    assert (await Gap.get(row.id)).label == "x"  # committed at the end of the block


async def test_db_execute_inside_a_rolled_back_transaction_is_undone(dbapp):
    row = await Gap.create(label="a")
    with pytest.raises(RuntimeError):
        async with db.transaction():
            await db.execute("update gap_rows set label = 'x'")
            raise RuntimeError("undo")
    assert (await Gap.get(row.id)).label == "a"


async def test_db_execute_outside_a_transaction_commits(dbapp):
    row = await Gap.create(label="a")
    await db.execute("update gap_rows set label = 'z'")
    await db.engine.dispose()  # a new connection sees it only if it was committed
    assert (await Gap.get(row.id)).label == "z"


def test_datetime_tz_is_an_alias_of_timezone():
    from ushka.orm.database import UTCDateTime

    assert isinstance(db.DateTime(tz=True).type, UTCDateTime)
    assert not isinstance(db.DateTime(tz=False, auto_now=True).type, UTCDateTime)
    assert isinstance(db.DateTime(timezone=True).type, UTCDateTime)
    with pytest.raises(TypeError):
        db.DateTime(tz=True, timezone=False)


async def test_host_routing_uses_the_trusted_host(workdir, make_app, call):
    (workdir / "ushka.toml").write_text('[security]\ntrusted_proxies = ["10.0.0.1"]\n')
    app = make_app()

    @app.get("/")
    async def home():
        return "site"

    @app.host("api.example.com").get("/")
    async def api():
        return "api"

    # An untrusted peer cannot pick the host with X-Forwarded-Host
    spoof = await call(app, "GET", "/", headers={"host": "www.example.com", "x-forwarded-host": "api.example.com"})
    assert spoof["body"] == "site"
    res = await call(app, "GET", "/", headers={"host": "api.example.com"})
    assert res["body"] == "api"


async def test_response_in_depends_is_used_as_is(app, call):
    async def key():
        raise HTTPResponse(Response({"error": "no key"}, status_code=401))

    @app.get("/x")
    async def x(k=Depends(key)):
        return "no"

    res = await call(app, "GET", "/x")
    assert res["status"] == 401 and "no key" in res["body"]
