"""Regression tests for the 0.4.1 security hardening."""

import pytest

from ushka.http.redirect import redirect
from ushka.http.response import Response


async def _send(response):
    messages = []

    async def send(message):
        messages.append(message)

    await response(send)
    return {bytes(k).decode(): bytes(v).decode() for k, v in messages[0]["headers"]}


# --- static files -----------------------------------------------------------


@pytest.fixture
def static_app(make_app, workdir):
    (workdir / "static").mkdir()
    (workdir / "static" / "ok.txt").write_text("PUBLIC")
    (workdir / "static_private").mkdir()
    (workdir / "static_private" / "secret.txt").write_text("SECRET")
    (workdir / "ushka.toml").write_text('[static]\nenable = true\n')
    return make_app()


async def test_static_serves_regular_file(static_app, call):
    res = await call(static_app, "GET", "/static/ok.txt")
    assert res["status"] == 200 and res["body"] == "PUBLIC"


@pytest.mark.parametrize(
    "path",
    [
        "/static/../static_private/secret.txt",  # sibling dir sharing the prefix
        "/static/../../etc/passwd",
        "/static/%2e%2e/static_private/secret.txt",
    ],
)
async def test_static_blocks_path_traversal(static_app, call, path):
    res = await call(static_app, "GET", path)
    assert res["status"] == 404
    assert "SECRET" not in res["body"]


async def test_static_missing_file_is_404_not_500(static_app, call):
    res = await call(static_app, "GET", "/static/nope.txt")
    assert res["status"] == 404


async def test_static_symlink_escape_is_blocked(static_app, call, workdir):
    (workdir / "static" / "link.txt").symlink_to(workdir / "static_private" / "secret.txt")
    res = await call(static_app, "GET", "/static/link.txt")
    assert res["status"] == 404


# --- response headers -------------------------------------------------------


async def test_header_values_keep_their_case():
    headers = await _send(redirect("/Users/AbC?Token=XyZ"))
    assert headers["location"] == "/Users/AbC?Token=XyZ"


@pytest.mark.parametrize("value", ["a\r\nSet-Cookie: x=1", "a\nb", "a\x00b"])
async def test_header_injection_is_rejected(value):
    with pytest.raises(ValueError):
        await _send(Response("x", headers={"X-Test": value}))


# --- request limits / error status codes ------------------------------------


async def test_oversized_body_returns_413(app, call):
    @app.post("/echo")
    async def echo(request):
        return await request.body()

    big = b"x" * (2048 * 1024 + 1)
    res = await call(app, "POST", "/echo", body=big)
    assert res["status"] == 413


async def test_invalid_form_encoding_returns_400(app, call):
    @app.post("/form")
    async def form(request):
        return await request.form()

    res = await call(
        app,
        "POST",
        "/form",
        body=b"\xff\xfe=1",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert res["status"] == 400


async def test_wrong_method_returns_405_with_allow_header(app, call):
    @app.get("/only-get")
    async def only_get():
        return "ok"

    res = await call(app, "POST", "/only-get")
    assert res["status"] == 405
    assert res["headers"]["allow"] == "GET, HEAD"


async def test_unknown_path_is_still_404(app, call):
    @app.get("/known")
    async def known():
        return "ok"

    assert (await call(app, "GET", "/unknown"))["status"] == 404


# --- session ----------------------------------------------------------------


def test_session_encode_failure_does_not_log_contents(caplog):
    from ushka.http.sessions import Session

    s = Session("k" * 32)
    s["password"] = "hunter2"
    s["bad"] = object()  # not JSON serializable

    assert s._encode() == ""
    assert "hunter2" not in caplog.text


def test_flash_with_pending_messages_marks_the_session_modified():
    from types import SimpleNamespace

    from ushka.http.sessions import Session
    from ushka.utils.flash import flash

    signed = Session("k" * 32)
    signed["_flashes"] = [["info", "older"]]
    cookie = signed._encode()

    session = Session("k" * 32, raw_cookie_value=cookie)
    assert not session.should_save
    flash(SimpleNamespace(session=session), "newer")
    assert session.should_save
    assert [m for _, m in session["_flashes"]] == ["older", "newer"]
