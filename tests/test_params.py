"""Typed parameters, request validation and Depends."""

import dataclasses
import json
import uuid
from enum import Enum
from typing import Annotated, Literal, Optional

from ushka import Body, Cookie, Depends, Field, Header, Query, Request, Response
from ushka.guard import Untrusted


def j(res):
    return json.loads(res["body"])


async def test_path_param_is_converted_to_its_annotation_and_loses_taint(app, call):
    @app.get("/items/[item_id]")
    async def item(item_id: int):
        return {"id": item_id, "plain": type(item_id) is int}

    assert j(await call(app, "GET", "/items/42")) == {"id": 42, "plain": True}
    bad = await call(app, "GET", "/items/abc")
    assert bad["status"] == 422
    assert j(bad)["detail"][0] == {"loc": ["path", "item_id"], "msg": "Input should be a valid integer", "type": "int_parsing"}
    assert "abc" not in bad["body"]  # input is not echoed back


async def test_unannotated_path_param_stays_untrusted(app, call):
    seen = {}

    @app.get("/u/[name]")
    async def user(name):
        seen["t"] = isinstance(name, Untrusted)
        return "ok"

    await call(app, "GET", "/u/ada")
    assert seen["t"] is True


async def test_str_params_stay_untrusted_but_numbers_do_not(app, call):
    seen = {}

    @app.get("/q")
    async def q(term: str, limit: int = 10):
        seen.update(term=isinstance(term, Untrusted), limit=type(limit))
        return "ok"

    await call(app, "GET", "/q", query=b"term=x&limit=5")
    assert seen == {"term": True, "limit": int}


async def test_query_defaults_required_and_limits(app, call):
    @app.get("/s")
    async def s(page: Annotated[int, Query(ge=1)] = 1, size: int = Query(10, le=50), tag: list[str] = Query([])):
        return {"page": page, "size": size, "tag": list(tag)}

    assert j(await call(app, "GET", "/s")) == {"page": 1, "size": 10, "tag": []}
    assert j(await call(app, "GET", "/s", query=b"tag=a&tag=b"))["tag"] == ["a", "b"]
    assert j(await call(app, "GET", "/s", query=b"tag=a"))["tag"] == ["a"]
    res = await call(app, "GET", "/s", query=b"page=0&size=99")
    kinds = {tuple(e["loc"]): e["type"] for e in j(res)["detail"]}
    assert kinds == {("query", "page"): "greater_than_equal", ("query", "size"): "less_than_equal"}  # all errors at once


async def test_missing_required_query(app, call):
    @app.get("/r")
    async def r(token: str):
        return "ok"

    res = await call(app, "GET", "/r")
    assert res["status"] == 422 and j(res)["detail"][0]["type"] == "missing"


async def test_header_and_cookie(app, call):
    @app.get("/h")
    async def h(user_agent: str = Header(), x_token: Optional[str] = Header(), sid: str = Cookie("none")):
        return {"ua": user_agent, "tok": x_token, "sid": sid}

    res = await call(app, "GET", "/h", headers={"User-Agent": "tests", "Cookie": "sid=abc"})
    assert j(res) == {"ua": "tests", "tok": None, "sid": "abc"}


@dataclasses.dataclass
class Item:
    name: Annotated[str, Field(min_length=2)]
    price: float
    tags: list[str] = dataclasses.field(default_factory=list)


async def test_json_body_into_dataclass(app, call):
    @app.post("/items")
    async def create(item: Item):
        return {"name": str(item.name), "price": item.price, "t": isinstance(item.name, Untrusted)}

    ok = await call(app, "POST", "/items", body=b'{"name":"pen","price":"2.5"}', headers={"content-type": "application/json"})
    assert j(ok) == {"name": "pen", "price": 2.5, "t": True}

    bad = await call(app, "POST", "/items", body=b'{"name":"p","price":"x","admin":true}', headers={"content-type": "application/json"})
    assert bad["status"] == 422
    assert {tuple(e["loc"]) for e in j(bad)["detail"]} == {("body", "name"), ("body", "price")}

    missing = await call(app, "POST", "/items", body=b"{}", headers={"content-type": "application/json"})
    assert {e["type"] for e in j(missing)["detail"]} == {"missing"}


async def test_unknown_body_fields_are_dropped_no_mass_assignment(app, call):
    @dataclasses.dataclass
    class Safe:
        name: str

    @app.post("/s2")
    async def s2(data: Safe):
        return {"fields": [f.name for f in dataclasses.fields(data)], "has_admin": hasattr(data, "is_admin")}

    res = await call(app, "POST", "/s2", body=b'{"name":"a","is_admin":true}')
    assert j(res) == {"fields": ["name"], "has_admin": False}


async def test_body_embed_with_two_body_params(app, call):
    @app.post("/two")
    async def two(a: Item, note: str = Body()):
        return {"n": str(note), "a": str(a.name)}

    res = await call(app, "POST", "/two", body=b'{"a":{"name":"xx","price":1},"note":"hi"}')
    assert j(res) == {"n": "hi", "a": "xx"}


async def test_enum_literal_and_uuid(app, call):
    class Color(Enum):
        red = "red"
        blue = "blue"

    @app.get("/c/[cid]")
    async def c(cid: uuid.UUID, color: Color, mode: Literal["a", "b"] = "a"):
        return {"cid": str(cid), "color": color.value, "mode": mode, "plain": type(mode) is str and not isinstance(mode, Untrusted)}

    cid = uuid.uuid4()
    res = await call(app, "GET", f"/c/{cid}", query=b"color=red&mode=b")
    assert j(res) == {"cid": str(cid), "color": "red", "mode": "b", "plain": True}
    assert (await call(app, "GET", "/c/nope", query=b"color=green&mode=z"))["status"] == 422


async def test_special_names_still_injected(app, call):
    @app.get("/sp")
    async def sp(request: Request, response: Response, config, page: int = 1):
        return {"p": request.path, "page": page, "has": bool(config)}

    assert j(await call(app, "GET", "/sp", query=b"page=3")) == {"p": "/sp", "page": 3, "has": True}


# -- Depends ---------------------------------------------------------------------


async def test_depends_runs_once_per_request_and_can_depend_on_others(app, call):
    calls = []

    def settings():
        calls.append("settings")
        return {"limit": 5}

    async def pager(page: int = 1, cfg: dict = Depends(settings)):
        calls.append("pager")
        return (page, cfg["limit"])

    @app.get("/d")
    async def d(p=Depends(pager), cfg=Depends(settings)):
        return {"p": p, "n": calls.count("settings")}

    assert j(await call(app, "GET", "/d", query=b"page=2")) == {"p": [2, 5], "n": 1}


async def test_depends_can_reject_with_an_http_error(app, call):
    from ushka.http.exceptions import HTTPForbidden

    def need_key(x_api_key: str = Header("")):
        if x_api_key != "k":
            raise HTTPForbidden(message="bad key")

    @app.get("/secure", )
    async def secure(_=Depends(need_key)):
        return "in"

    assert (await call(app, "GET", "/secure"))["status"] == 403
    assert (await call(app, "GET", "/secure", headers={"X-Api-Key": "k"}))["status"] == 200


async def test_yield_dependency_cleans_up_even_on_error(app, call):
    log = []

    def session():
        log.append("open")
        try:
            yield "db"
        finally:
            log.append("close")

    @app.get("/y")
    async def y(db=Depends(session)):
        return db

    @app.get("/boom")
    async def boom(db=Depends(session)):
        raise RuntimeError("x")

    assert (await call(app, "GET", "/y"))["body"] == "db" and log == ["open", "close"]
    assert (await call(app, "GET", "/boom"))["status"] == 500 and log == ["open", "close", "open", "close"]


async def test_dependency_overrides(app, call):
    def real():
        return "real"

    @app.get("/o")
    async def o(v=Depends(real)):
        return v

    assert (await call(app, "GET", "/o"))["body"] == "real"
    app.dependency_overrides[real] = lambda: "fake"
    assert (await call(app, "GET", "/o"))["body"] == "fake"


async def test_depends_in_annotated_and_shared_response(app, call):
    def tag(response: Response):
        response.headers["X-Tag"] = "t"
        return 1

    @app.get("/a")
    async def a(response: Response, n: Annotated[int, Depends(tag)]):
        return "ok", 200, dict(response.headers)

    res = await call(app, "GET", "/a")
    assert res["headers"]["x-tag"] == "t"
