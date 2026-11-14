"""Security middleware (on by default) and the middleware chain."""

import pytest

from ushka import Response


def _app(make_app, workdir, toml=""):
    if toml:
        (workdir / "ushka.toml").write_text(toml)
    app = make_app()

    @app.get("/")
    async def home():
        return {"ok": True}

    @app.post("/act")
    async def act():
        return {"done": True}

    return app


async def test_headers_are_on_by_default(make_app, workdir, call):
    res = await call(_app(make_app, workdir), "GET", "/")
    h = res["headers"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "strict-transport-security" not in h  # plain http


async def test_error_pages_get_headers_too(make_app, workdir, call):
    res = await call(_app(make_app, workdir), "GET", "/nope")
    assert res["status"] == 404 and res["headers"]["x-content-type-options"] == "nosniff"


async def test_route_headers_win_and_csp_can_be_replaced_or_off(make_app, workdir, call):
    app = _app(make_app, workdir, '[security]\ncsp = "off"\n')

    @app.get("/own")
    async def own():
        return "x", 200, {"X-Frame-Options": "SAMEORIGIN"}

    res = await call(app, "GET", "/own")
    assert res["headers"]["x-frame-options"] == "SAMEORIGIN"
    assert "content-security-policy" not in res["headers"]


async def test_hsts_only_over_https(make_app, workdir, call):
    app = _app(make_app, workdir)
    seen = {}

    async def spy(request, call_next):
        request.scope["scheme"] = "https"
        return await call_next(request)

    # the scheme is read after the chain, so flipping it in a middleware is enough
    app.add_middleware(spy)
    res = await call(app, "GET", "/")
    assert "max-age=31536000" in res["headers"]["strict-transport-security"]


@pytest.mark.parametrize(
    "headers, status",
    [
        ({}, 200),  # curl, mobile app, server to server
        ({"Sec-Fetch-Site": "same-origin"}, 200),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Sec-Fetch-Site": "same-site"}, 403),
        ({"Origin": "https://evil.example", "Host": "app.test"}, 403),
        ({"Origin": "null", "Host": "app.test"}, 403),
        ({"Origin": "https://app.test", "Host": "app.test"}, 200),
    ],
)
async def test_csrf_blocks_cross_site_writes(make_app, workdir, call, headers, status):
    res = await call(_app(make_app, workdir), "POST", "/act", headers=headers)
    assert res["status"] == status


async def test_csrf_never_blocks_safe_methods(make_app, workdir, call):
    res = await call(_app(make_app, workdir), "GET", "/", headers={"Sec-Fetch-Site": "cross-site"})
    assert res["status"] == 200


async def test_csrf_trusted_origins_exempt_paths_and_off(make_app, workdir, call):
    evil = {"Origin": "https://partner.example", "Host": "app.test"}
    toml = '[security]\ncsrf_trusted_origins = ["https://partner.example"]\n'
    assert (await call(_app(make_app, workdir, toml), "POST", "/act", headers=evil))["status"] == 200


async def test_csrf_exempt_path(make_app, workdir, call):
    toml = '[security]\ncsrf_exempt_paths = ["/act"]\n'
    res = await call(_app(make_app, workdir, toml), "POST", "/act", headers={"Sec-Fetch-Site": "cross-site"})
    assert res["status"] == 200


async def test_csrf_can_be_turned_off(make_app, workdir, call):
    res = await call(_app(make_app, workdir, "[security]\ncsrf = false\n"), "POST", "/act", headers={"Sec-Fetch-Site": "cross-site"})
    assert res["status"] == 200


async def test_trusted_hosts(make_app, workdir, call):
    app = _app(make_app, workdir, '[security]\nallowed_hosts = ["app.test", "*.example.com"]\n')
    assert (await call(app, "GET", "/", headers={"Host": "app.test:8000"}))["status"] == 200
    assert (await call(app, "GET", "/", headers={"Host": "api.example.com"}))["status"] == 200
    assert (await call(app, "GET", "/", headers={"Host": "evil.test"}))["status"] == 400
    assert (await call(app, "GET", "/", headers={"Host": "evilexample.com"}))["status"] == 400


async def test_cors_off_by_default(make_app, workdir, call):
    res = await call(_app(make_app, workdir), "GET", "/", headers={"Origin": "https://a.test"})
    assert "access-control-allow-origin" not in res["headers"]


async def test_cors_allowed_origin_and_preflight(make_app, workdir, call):
    app = _app(make_app, workdir, '[security]\ncors_origins = ["https://a.test"]\ncors_credentials = true\n')
    res = await call(app, "GET", "/", headers={"Origin": "https://a.test"})
    assert res["headers"]["access-control-allow-origin"] == "https://a.test"
    assert res["headers"]["access-control-allow-credentials"] == "true"
    assert "origin" in res["headers"]["vary"].lower()

    pre = await call(app, "OPTIONS", "/act", headers={
        "Origin": "https://a.test", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert pre["status"] == 204 and "POST" in pre["headers"]["access-control-allow-methods"]
    assert pre["headers"]["access-control-allow-headers"] == "content-type"

    bad = await call(app, "OPTIONS", "/act", headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"})
    assert bad["status"] == 403

    # a CORS-allowed origin may also write: it is trusted for CSRF too
    ok = await call(app, "POST", "/act", headers={"Origin": "https://a.test", "Host": "app.test", "Sec-Fetch-Site": "cross-site"})
    assert ok["status"] == 200


async def test_cors_wildcard_with_credentials_is_refused(make_app, workdir):
    with pytest.raises(ValueError, match="cors_credentials"):
        _app(make_app, workdir, '[security]\ncors_origins = ["*"]\ncors_credentials = true\n')


async def test_cors_wildcard_answers_star(make_app, workdir, call):
    app = _app(make_app, workdir, '[security]\ncors_origins = ["*"]\n')
    res = await call(app, "GET", "/", headers={"Origin": "https://any.test"})
    assert res["headers"]["access-control-allow-origin"] == "*"


async def test_env_var_lists_are_comma_separated(make_app, workdir, call, monkeypatch):
    monkeypatch.setenv("USHKA_SECURITY_ALLOWED_HOSTS", "app.test, other.test")
    app = _app(make_app, workdir)
    assert (await call(app, "GET", "/", headers={"Host": "other.test"}))["status"] == 200
    assert (await call(app, "GET", "/", headers={"Host": "x.test"}))["status"] == 400


async def test_user_middleware_order_and_response_edit(make_app, workdir, call):
    app = _app(make_app, workdir)
    order = []

    @app.middleware
    async def first(request, call_next):
        order.append("first-in")
        res = await call_next(request)
        res.headers["X-First"] = "1"
        order.append("first-out")
        return res

    @app.middleware
    def second(request, call_next):  # sync middleware that returns the awaitable
        order.append("second")
        return call_next(request)

    res = await call(app, "GET", "/")
    assert order == ["first-in", "second", "first-out"]
    assert res["headers"]["x-first"] == "1" and res["headers"]["x-content-type-options"] == "nosniff"


async def test_middleware_can_short_circuit_and_sees_errors_as_responses(make_app, workdir, call):
    app = _app(make_app, workdir)
    seen = []

    @app.middleware
    async def gate(request, call_next):
        if request.path == "/blocked":
            return "no", 401
        res = await call_next(request)
        seen.append(res.status_code)
        return res

    assert (await call(app, "GET", "/blocked"))["status"] == 401
    assert (await call(app, "GET", "/missing"))["status"] == 404 and seen == [404]
