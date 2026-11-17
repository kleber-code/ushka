"""A NUL byte in client text is a 400 at the door, not a 500 from the database later."""

import pytest

from ushka.http.exceptions import HTTPBadRequest, reject_nul


@pytest.fixture
def nul_app(make_app, workdir):
    (workdir / "ushka.toml").write_text("[app]\nauto_discover = false\n")
    app = make_app()

    @app.get("/q")
    async def q(request):
        return {"v": str(request.query.get("a", ""))}

    @app.get("/p/[name]")
    async def p(name):
        return {"n": str(name)}

    @app.post("/j")
    async def j(request):
        return await request.json()

    @app.post("/f")
    async def f(request):
        return {k: str(v) for k, v in (await request.form()).items()}

    return app


async def test_query_json_and_form_with_nul_are_400(nul_app, call):
    assert (await call(nul_app, "GET", "/q", query=b"a=x%00y"))["status"] == 400
    assert (await call(nul_app, "POST", "/j", body=b'{"a": ["ok", {"b": "x\\u0000y"}]}', headers={"content-type": "application/json"}))["status"] == 400
    res = await call(nul_app, "POST", "/f", body=b"a=x%00y", headers={"content-type": "application/x-www-form-urlencoded"})
    assert res["status"] == 400 and "x\x00y" not in res["body"]


async def test_path_parameter_with_nul_is_400(nul_app, call):
    res = await call(nul_app, "GET", "/p/x\x00y")
    assert res["status"] == 400


async def test_normal_input_is_untouched(nul_app, call):
    assert (await call(nul_app, "GET", "/q", query=b"a=hello"))["status"] == 200
    assert (await call(nul_app, "GET", "/p/ana"))["status"] == 200
    ok = await call(nul_app, "POST", "/j", body='{"a": "olá \\n\\t"}'.encode(), headers={"content-type": "application/json"})
    assert ok["status"] == 200


async def test_the_guard_off_does_not_turn_the_check_off(make_app, workdir, call):
    (workdir / "ushka.toml").write_text("[app]\nauto_discover = false\n[security]\ntaint = false\n")
    app = make_app()

    @app.get("/q")
    async def q(request):
        return {"v": request.query.get("a", "")}

    assert (await call(app, "GET", "/q", query=b"a=x%00y"))["status"] == 400


def test_reject_nul_walks_nested_data_and_keys():
    assert reject_nul({"a": ["b", ("c", "d")]}) == {"a": ["b", ("c", "d")]}
    for bad in ("a\x00", ["ok", "\x00"], {"k": {"n": "\x00"}}, {"\x00": 1}):
        with pytest.raises(HTTPBadRequest):
            reject_nul(bad)
