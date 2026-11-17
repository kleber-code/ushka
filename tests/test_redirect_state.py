"""`raise HTTPRedirect(url)` keeps the cookies, session and flash messages set before it."""

import pytest

from ushka import HTTPRedirect, Request, UploadFile
from ushka.guard import UnsafeValueError, Untrusted
from ushka.http.exceptions import HTTPForbidden
from ushka.templating.flash import flash, get_flashed_messages


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


async def test_server_side_session_survives_raise_redirect_with_flash_and_upload(workdir, make_app, call):
    """Database sessions + `raise HTTPRedirect` + flash + a multipart upload, in one request."""
    import json

    (workdir / "ushka.toml").write_text(
        f'[session]\nstore = "database"\n[database]\nurl = "sqlite:///{workdir}/s.db"\n'
    )
    app = make_app()

    @app.post("/upload")
    async def upload(request: Request, doc: UploadFile):
        request.session["next"] = "/after"
        flash(request, f"Saved {doc.size} bytes")
        raise HTTPRedirect("/done")

    @app.get("/done")
    async def done(request: Request):
        return {"next": request.session.get("next"), "messages": get_flashed_messages(request)}

    @app.post("/crash")
    async def crash(request: Request):
        request.session["ghost"] = 1
        raise RuntimeError("boom")

    boundary = "xBx"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="doc"; filename="a.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\nhello\r\n--{boundary}--\r\n"
    ).encode()
    headers = {"content-type": f"multipart/form-data; boundary={boundary}"}

    first = await call(app, "POST", "/upload", body=body, headers=headers)
    assert first["status"] == 302 and first["headers"]["location"] == "/done"
    cookie = first["headers"]["set-cookie"].split(";")[0]
    assert "after" not in cookie  # only an id travels; the data is in the database

    second = await call(app, "GET", "/done", headers={"cookie": cookie})
    data = json.loads(second["body"])
    assert data["next"] == "/after" and data["messages"] == ["Saved 5 bytes"]

    crashed = await call(app, "POST", "/crash", headers={"cookie": cookie})
    assert crashed["status"] == 500
    again = await call(app, "GET", "/done", headers={"cookie": cookie})
    assert "ghost" not in again["body"]
