"""`raise HTTPRedirect(url)` keeps the cookies, session and flash messages set before it."""

import pytest

from ushka import HTTPRedirect, Request
from ushka.guard import UnsafeValueError, Untrusted
from ushka.http.exceptions import HTTPForbidden
from ushka.utils import flash, get_flashed_messages


@pytest.fixture(autouse=True)
def secret_key(monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", "k" * 40)


async def test_raise_redirect_sends_location_and_status(app, call):
    @app.get("/old")
    async def old():
        raise HTTPRedirect("/new", 301)

    result = await call(app, "GET", "/old")

    assert result["status"] == 301
    assert result["headers"]["location"] == "/new"


async def test_flash_survives_raise_redirect(app, call):
    @app.post("/save")
    async def save(request: Request):
        flash(request, "Saved!")
        raise HTTPRedirect("/done")

    @app.get("/done")
    async def done(request: Request):
        return {"messages": get_flashed_messages(request)}

    first = await call(app, "POST", "/save")
    assert first["status"] == 302
    cookie = first["headers"]["set-cookie"].split(";")[0]

    second = await call(app, "GET", "/done", headers={"cookie": cookie})
    assert "Saved!" in second["body"]


async def test_session_value_survives_raise_redirect(app, call):
    @app.get("/private")
    async def private(request: Request):
        request.session["next"] = "/private"
        raise HTTPRedirect("/login")

    @app.get("/login")
    async def login(request: Request):
        return {"next": request.session.get("next")}

    first = await call(app, "GET", "/private")
    cookie = first["headers"]["set-cookie"].split(";")[0]
    second = await call(app, "GET", "/login", headers={"cookie": cookie})

    assert '"/private"' in second["body"]


async def test_cookie_set_before_raise_is_sent(app, call):
    @app.get("/go")
    async def go(request: Request):
        request.cookies.set("seen", "1")
        raise HTTPRedirect("/")

    result = await call(app, "GET", "/go")

    assert "seen=1" in result["headers"]["set-cookie"]


async def test_session_changes_are_kept_on_a_4xx_but_not_on_a_crash(app, call):
    @app.get("/denied")
    async def denied(request: Request):
        request.session["tried"] = "yes"
        raise HTTPForbidden()

    @app.get("/boom")
    async def boom(request: Request):
        request.session["tried"] = "yes"
        raise RuntimeError("boom")

    assert "set-cookie" in (await call(app, "GET", "/denied"))["headers"]
    crashed = await call(app, "GET", "/boom")
    assert crashed["status"] == 500
    assert "set-cookie" not in crashed["headers"]


async def test_untouched_request_sets_no_cookie_on_redirect(app, call):
    @app.get("/go")
    async def go():
        raise HTTPRedirect("/")

    assert "set-cookie" not in (await call(app, "GET", "/go"))["headers"]


def test_redirect_to_untrusted_url_is_refused():
    with pytest.raises(UnsafeValueError):
        HTTPRedirect(Untrusted("https://evil.example", "query:next"))
