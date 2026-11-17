"""Server-side (revocable) sessions: `[session] store = "database"`, and the cookie fallback."""

from __future__ import annotations

import asyncio
import time

import pytest

from ushka.sessions.stores import SessionRecord, SessionStore, revoke_user_sessions

KEY = "k" * 48


class MemoryStore(SessionStore):
    """A test double: the framework ships no in-process store (it breaks with several workers)."""

    def __init__(self):
        self._records = {}

    async def load(self, key):
        rec = self._records.get(key)
        return None if rec is None else SessionRecord(rec.key, rec.data, rec.user_id, rec.created_at, rec.last_seen)

    async def save(self, record):
        self._records[record.key] = SessionRecord(record.key, record.data, record.user_id, record.created_at, record.last_seen)

    async def touch(self, key, last_seen):
        if key in self._records:
            self._records[key].last_seen = last_seen

    async def delete(self, key):
        self._records.pop(key, None)

    async def delete_user(self, user_id):
        doomed = [k for k, r in self._records.items() if r.user_id == user_id]
        for k in doomed:
            del self._records[k]
        return len(doomed)

    async def purge(self, created_before, seen_before):
        doomed = [k for k, r in self._records.items()
                  if (created_before is not None and r.created_at < created_before)
                  or (seen_before is not None and r.last_seen < seen_before)]
        for k in doomed:
            del self._records[k]
        return len(doomed)


def cookie_of(res):
    """`name=value` of the session cookie in a response (or None)."""
    header = res["headers"].get("set-cookie")
    if not header or "Max-Age=0" in header:
        return None
    return header.split(";", 1)[0]


@pytest.fixture
def setup(workdir, make_app, monkeypatch):
    def build(store="memory", extra="", routes=True):
        monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
        # "memory" is the test double above, plugged in like any custom store
        toml_store = "cookie" if store == "memory" else store
        (workdir / "ushka.toml").write_text(f'[session]\nstore = "{toml_store}"\n{extra}')
        app = make_app()
        if store == "memory":
            app.session_store = MemoryStore()
        if routes:
            add_routes(app)
        return app

    return build


def add_routes(app):
    @app.post("/login")
    async def login(request):
        request.session["user_id"] = 7
        request.session["name"] = "ana"
        return {"ok": True}

    @app.get("/me")
    async def me(request):
        return {"user": request.session.get("user_id"), "name": request.session.get("name")}

    @app.post("/logout")
    async def logout(request):
        request.session.clear()
        return {"ok": True}

    @app.post("/rotate")
    async def rotate(request):
        request.session.rotate()
        return {"ok": True}

    @app.post("/big")
    async def big(request):
        request.session["blob"] = "x" * 100_000
        return {"ok": True}

    @app.post("/revoke-all")
    async def revoke_all(request):
        return {"n": await revoke_user_sessions(request, 7)}


async def login(call, app, user=7):
    res = await call(app, "POST", "/login")
    assert res["status"] == 200
    return cookie_of(res)


async def me(call, app, cookie):
    res = await call(app, "GET", "/me", headers={"cookie": cookie} if cookie else None)
    import json

    return json.loads(res["body"])


async def test_login_then_logout_revokes_a_stolen_cookie(setup, call):
    app = setup()
    cookie = await login(call, app)
    assert cookie and cookie.startswith("_ushka_session=")
    assert (await me(call, app, cookie))["user"] == 7

    stolen = cookie
    res = await call(app, "POST", "/logout", headers={"cookie": cookie})
    assert "Max-Age=0" in res["headers"]["set-cookie"]
    assert (await me(call, app, stolen))["user"] is None  # the copy is dead


async def test_cookie_carries_only_an_opaque_id(setup, call):
    app = setup()
    cookie = await login(call, app)
    value = cookie.split("=", 1)[1]
    assert "ana" not in value and "user" not in value
    sid, sig = value.split(".")
    assert len(sid) >= 40 and len(sig) == 64
    res = await call(app, "POST", "/login")
    assert "HttpOnly" in res["headers"]["set-cookie"] and "SameSite=lax" in res["headers"]["set-cookie"]
    assert cookie_of(res) != cookie  # random each time


async def test_store_keeps_a_hash_not_the_id(setup, call):
    app = setup()
    cookie = await login(call, app)
    sid = cookie.split("=", 1)[1].split(".")[0]
    from ushka.sessions.stores import get_store

    keys = list(get_store(app)._records)
    assert len(keys) == 1 and sid not in keys[0]


async def test_tampered_or_forged_cookie_is_rejected(setup, call):
    app = setup()
    cookie = await login(call, app)
    name, value = cookie.split("=", 1)
    sid, sig = value.split(".")
    for bad in (f"{name}={sid}.{'0' * 64}", f"{name}={sid}x.{sig}", f"{name}={sid}", f"{name}=.{sig}", f"{name}=junk", f"{name}="):
        assert (await me(call, app, bad))["user"] is None


async def test_a_cookie_signed_with_another_key_is_rejected(setup, call, monkeypatch):
    app = setup()
    cookie = await login(call, app)
    from ushka.sessions.session import ServerSession

    sid = cookie.split("=", 1)[1].split(".")[0]
    forged = ServerSession(None, "z" * 48)
    forged_cookie = f"_ushka_session={sid}.{forged._sign(sid.encode()).decode()}"
    assert (await me(call, app, forged_cookie))["user"] is None


async def test_rotate_changes_the_id_and_kills_the_old_one(setup, call):
    app = setup()
    old = await login(call, app)
    res = await call(app, "POST", "/rotate", headers={"cookie": old})
    new = cookie_of(res)
    assert new and new != old
    assert (await me(call, app, new))["name"] == "ana"  # data kept
    assert (await me(call, app, old))["user"] is None  # fixation id is dead


async def test_logging_in_on_an_existing_id_rotates_it(setup, call):
    app = setup()

    @app.post("/touch")
    async def touch(request):
        request.session["seen"] = True
        return {}

    planted = cookie_of(await call(app, "POST", "/touch"))
    res = await call(app, "POST", "/login", headers={"cookie": planted})
    new = cookie_of(res)
    assert new and new != planted
    assert (await me(call, app, planted))["user"] is None
    assert (await me(call, app, new))["user"] == 7


async def test_absolute_expiry(setup, call):
    app = setup(extra="max_age = 100\n")
    cookie = await login(call, app)
    from ushka.sessions.stores import get_store

    store = get_store(app)
    rec = next(iter(store._records.values()))
    rec.created_at -= 101
    assert (await me(call, app, cookie))["user"] is None
    assert not store._records  # the expired record is removed


async def test_idle_expiry_and_touch(setup, call):
    app = setup(extra="idle_timeout = 100\n")
    cookie = await login(call, app)
    from ushka.sessions.stores import get_store

    store = get_store(app)
    rec = next(iter(store._records.values()))
    rec.last_seen -= 50
    assert (await me(call, app, cookie))["user"] == 7
    assert time.time() - rec.last_seen < 5  # activity renewed it
    rec.last_seen -= 101
    assert (await me(call, app, cookie))["user"] is None


async def test_idle_timeout_off_by_default(setup, call):
    app = setup()
    cookie = await login(call, app)
    from ushka.sessions.stores import get_store

    next(iter(get_store(app)._records.values())).last_seen -= 10**6
    assert (await me(call, app, cookie))["user"] == 7


async def test_revoke_every_session_of_a_user(setup, call):
    app = setup()
    a, b = await login(call, app), await login(call, app)
    assert (await me(call, app, a))["user"] == 7 and (await me(call, app, b))["user"] == 7
    res = await call(app, "POST", "/revoke-all", headers={"cookie": a})
    assert '"n":2' in res["body"].replace(" ", "")
    assert (await me(call, app, a))["user"] is None
    assert (await me(call, app, b))["user"] is None


async def test_revoking_one_user_leaves_the_others(setup, call):
    app = setup()
    mine = await login(call, app)

    @app.post("/login2")
    async def login2(request):
        request.session["user_id"] = 8
        return {}

    theirs = cookie_of(await call(app, "POST", "/login2"))
    assert await revoke_user_sessions(app, 7) == 1
    assert (await me(call, app, mine))["user"] is None
    assert (await me(call, app, theirs))["user"] == 8


async def test_the_four_kb_limit_is_gone(setup, call):
    app = setup()
    res = await call(app, "POST", "/big")
    cookie = cookie_of(res)
    assert cookie and len(cookie) < 200

    @app.get("/blob")
    async def blob(request):
        return {"n": len(request.session.get("blob", ""))}

    res = await call(app, "GET", "/blob", headers={"cookie": cookie})
    assert '"n":100000' in res["body"].replace(" ", "")


async def test_values_must_be_json_and_are_not_logged(setup, call, caplog):
    app = setup()

    @app.post("/bad")
    async def bad(request):
        request.session["password"] = "hunter2"
        request.session["obj"] = object()
        return {}

    res = await call(app, "POST", "/bad")
    assert res["status"] == 500
    assert "hunter2" not in caplog.text and "hunter2" not in res["body"]


async def test_untouched_sessions_set_no_cookie(setup, call):
    app = setup()
    res = await call(app, "GET", "/me")
    assert "set-cookie" not in res["headers"]


async def test_custom_cookie_name(setup, call):
    app = setup(extra='cookie_name = "sid"\n')
    cookie = await login(call, app)
    assert cookie.startswith("sid=")
    assert (await me(call, app, cookie))["user"] == 7


async def test_custom_store_can_be_plugged_in(setup, call):
    class Counting(MemoryStore):
        saves = 0

        async def save(self, record):
            type(self).saves += 1
            await super().save(record)

    app = setup(store="cookie")
    app.session_store = Counting()
    cookie = await login(call, app)
    assert Counting.saves == 1
    assert (await me(call, app, cookie))["user"] == 7
    assert issubclass(Counting, SessionStore)


async def test_unknown_store_is_an_error(setup):
    from ushka.sessions.stores import get_store

    app = setup(store="redis")
    with pytest.raises(ValueError, match="redis"):
        get_store(app)


async def test_database_store_end_to_end(setup, call, workdir):
    app = setup(store="database", extra=f'table = "web_sessions"\n[database]\nurl = "sqlite:///{workdir}/s.db"\n')
    cookie = await login(call, app)
    assert (await me(call, app, cookie))["name"] == "ana"
    second = await login(call, app)

    # rotation and logout against the database
    res = await call(app, "POST", "/rotate", headers={"cookie": cookie})
    new = cookie_of(res)
    assert (await me(call, app, cookie))["user"] is None
    assert (await me(call, app, new))["user"] == 7

    await call(app, "POST", "/logout", headers={"cookie": new})
    assert (await me(call, app, new))["user"] is None

    assert await revoke_user_sessions(app, 7) == 1  # `second` was still alive
    assert (await me(call, app, second))["user"] is None

    from ushka.sessions.stores import get_store

    store = get_store(app)
    assert await store.purge(None, None) == 0
    await store._engine.dispose()
    assert (workdir / "s.db").exists()


async def test_database_store_expiry_and_purge(workdir):
    from ushka.sessions.stores import DatabaseStore, SessionRecord

    store = DatabaseStore(f"sqlite:///{workdir}/p.db")
    now = time.time()
    await store.save(SessionRecord("old", "{}", "1", now - 1000, now - 1000))
    await store.save(SessionRecord("idle", "{}", None, now, now - 500))
    await store.save(SessionRecord("fresh", "{}", None, now, now))
    await store.touch("missing", now)  # never creates a row
    assert await store.load("missing") is None
    assert await store.purge(now - 100, now - 100) == 2
    assert (await store.load("fresh")).data == "{}"
    await store.save(SessionRecord("fresh", '{"a":1}', "2", now, now))  # upsert
    assert (await store.load("fresh")).user_id == "2"
    await store._engine.dispose()


def test_database_table_name_is_validated(workdir):
    from ushka.sessions.stores import DatabaseStore

    with pytest.raises(ValueError):
        DatabaseStore("sqlite:///x.db", "sessions; DROP TABLE users")


async def test_memory_store_is_isolated_from_callers():
    store = MemoryStore()
    rec = SessionRecord("k", "{}", None, 1.0, 1.0)
    await store.save(rec)
    rec.data = "changed"
    assert (await store.load("k")).data == "{}"


# --- the default is untouched --------------------------------------------------


async def test_default_is_still_the_signed_cookie(workdir, make_app, call, monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    app = make_app()
    add_routes(app)
    from ushka.sessions.stores import get_store
    from ushka.sessions.session import ServerSession, Session

    assert get_store(app) is None
    res = await call(app, "POST", "/login")
    cookie = cookie_of(res)
    assert cookie.count(".") == 2 and "ana" not in cookie.split("=", 1)[1].replace("YW5h", "")  # base64 payload
    assert (await me(call, app, cookie))["user"] == 7
    # no server state: a "logged out" copy still works, as documented
    await call(app, "POST", "/logout", headers={"cookie": cookie})
    assert (await me(call, app, cookie))["user"] == 7
    assert not issubclass(Session, ServerSession)


def test_settings_defaults_keep_the_cookie_behaviour():
    from ushka.core.settings import DEFAULTS

    s = DEFAULTS["session"]
    assert s["store"] == "cookie" and s["max_age"] == 1209600 and s["cookie_name"] == "_ushka_session"
    assert s["idle_timeout"] == 0


def test_missing_secret_still_explains(workdir, make_app, monkeypatch):
    monkeypatch.delenv("USHKA_APP_SECRET_KEY", raising=False)
    (workdir / "ushka.toml").write_text('[session]\nstore = "cookie"\n')
    app = make_app()
    app.session_store = MemoryStore()
    from ushka.http.request import Request

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    req = Request(app, scope, receive)
    asyncio.run(req.load_session())  # must not raise
    with pytest.raises(RuntimeError, match="secret key"):
        _ = req.session


# --- no database, no server-side sessions ---------------------------------------


async def test_database_store_without_a_database_falls_back_to_cookies(workdir, make_app, call, monkeypatch, caplog):
    import logging

    from ushka.sessions.stores import get_store

    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("USHKA_DB_URL", raising=False)
    (workdir / "ushka.toml").write_text('[session]\nstore = "database"\n')  # no [database] url
    app = make_app()
    add_routes(app)
    with caplog.at_level(logging.WARNING):
        assert get_store(app) is None and get_store(app) is None
    warnings = [r for r in caplog.records if "needs a database" in r.getMessage()]
    assert len(warnings) == 1, "warned once, not on every request"
    cookie = await login(call, app)
    assert cookie.count(".") == 2  # a signed cookie, not an id
    assert (await me(call, app, cookie))["user"] == 7
    with pytest.raises(RuntimeError, match="database"):
        await revoke_user_sessions(app, 7)


async def test_a_configured_database_turns_server_sessions_on(workdir, make_app, call, monkeypatch):
    from ushka.sessions.stores import DatabaseStore, get_store

    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{workdir}/env.db")  # the environment counts too
    (workdir / "ushka.toml").write_text('[session]\nstore = "database"\n')
    app = make_app()
    assert isinstance(get_store(app), DatabaseStore)


def test_the_memory_store_is_gone_from_the_settings(workdir, make_app, monkeypatch):
    from ushka.sessions.stores import get_store

    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    (workdir / "ushka.toml").write_text('[session]\nstore = "memory"\n')
    with pytest.raises(ValueError, match='"cookie" or "database"'):
        get_store(make_app())


async def test_database_store_releases_its_connections_at_shutdown(workdir, make_app, monkeypatch):
    from ushka.sessions.stores import DatabaseStore, get_store

    monkeypatch.setenv("USHKA_APP_SECRET_KEY", KEY)
    (workdir / "ushka.toml").write_text(f'[session]\nstore = "database"\n[database]\nurl = "sqlite:///{workdir}/c.db"\n')
    app = make_app()
    store = get_store(app)
    assert isinstance(store, DatabaseStore)
    closed = []
    real = store.close

    async def spy():
        closed.append(True)
        await real()

    store.close = spy
    scope = {"type": "lifespan"}
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent = []

    async def receive():
        return next(messages)

    async def send(m):
        sent.append(m["type"])

    await app(scope, receive, send)
    assert closed == [True] and sent[-1] == "lifespan.shutdown.complete"
