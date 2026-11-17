"""A whole dataclass from an HTML form, and answering invalid forms per route."""

import dataclasses
import json
from datetime import date
from typing import Annotated, Optional

from ushka import Field, Form, RequestValidationError, Response, on_invalid
from ushka.guard import Untrusted

FORM = {"content-type": "application/x-www-form-urlencoded"}


@dataclasses.dataclass
class Lead:
    name: Annotated[str, Field(min_length=2, max_length=20)]
    email: str
    age: Optional[int] = None
    newsletter: bool = False
    tags: list[str] = dataclasses.field(default_factory=list)
    born: Optional[date] = None


@dataclasses.dataclass
class Safe:
    name: str


@dataclasses.dataclass
class Upload:
    title: str
    doc: dict
    tags: list[str] = dataclasses.field(default_factory=list)


def multipart(fields, files=None):
    b = "XBOUNDARY"
    out = b""
    for k, v in fields:
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, data) in (files or {}).items():
        out += (
            f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
        ).encode() + data + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return out, {"content-type": f"multipart/form-data; boundary={b}"}


def make(app):
    seen = {}

    @app.post("/lead")
    async def lead(data: Annotated[Lead, Form()]):
        seen["lead"] = data
        return {"ok": True}

    return seen


async def test_urlencoded_fills_dataclass_with_conversion(app, call):
    seen = make(app)
    body = b"name=Ada&email=a%40b.c&age=36&newsletter=on&tags=x&tags=y&born=1990-01-02"
    res = await call(app, "POST", "/lead", body=body, headers=FORM)
    assert res["status"] == 200
    lead = seen["lead"]
    assert lead.age == 36 and type(lead.age) is int
    assert lead.newsletter is True
    assert lead.tags == ["x", "y"]
    assert lead.born == date(1990, 1, 2)
    assert isinstance(lead.name, Untrusted)  # strings stay the client's


async def test_missing_checkbox_false_and_empty_number_is_none(app, call):
    seen = make(app)
    res = await call(app, "POST", "/lead", body=b"name=Ada&email=e&age=&born=", headers=FORM)
    assert res["status"] == 200
    assert seen["lead"].newsletter is False
    assert seen["lead"].age is None and seen["lead"].born is None
    assert seen["lead"].tags == []


async def test_single_value_is_a_list(app, call):
    seen = make(app)
    await call(app, "POST", "/lead", body=b"name=Ada&email=e&tags=only", headers=FORM)
    assert seen["lead"].tags == ["only"]


async def test_undeclared_fields_are_dropped_no_mass_assignment(app, call):
    got = {}

    @app.post("/safe")
    async def safe(data: Annotated[Safe, Form()]):
        got["d"] = data
        return "ok"

    res = await call(app, "POST", "/safe", body=b"name=a&is_admin=1&role=root", headers=FORM)
    assert res["status"] == 200
    assert dataclasses.asdict(got["d"]).keys() == {"name"}
    assert not hasattr(got["d"], "is_admin")


async def test_default_error_is_json_422_without_echo(app, call):
    make(app)
    res = await call(app, "POST", "/lead", body=b"name=A&age=zzzsecret", headers=FORM)
    assert res["status"] == 422
    detail = json.loads(res["body"])["detail"]
    locs = {tuple(e["loc"]) for e in detail}
    assert {("form", "name"), ("form", "email"), ("form", "age")} <= locs
    assert "zzzsecret" not in res["body"]


async def test_multipart_fields_and_files(app, call):
    seen = {}

    @app.post("/up")
    async def up(data: Annotated[Upload, Form()]):
        seen["d"] = data
        return "ok"

    body, headers = multipart([("title", "T"), ("tags", "a"), ("tags", "b")], {"doc": ("a.txt", b"hello")})
    res = await call(app, "POST", "/up", body=body, headers=headers)
    assert res["status"] == 200, res["body"]
    assert seen["d"].tags == ["a", "b"]
    assert seen["d"].doc["filename"] == "a.txt"


async def test_body_size_limit_still_applies(app, call):
    make(app)
    big = b"name=Ada&email=" + b"x" * (2 * 1024 * 1024)
    res = await call(app, "POST", "/lead", body=big, headers=FORM)
    assert res["status"] == 413


async def test_field_limits_apply_to_form(app, call):
    make(app)
    res = await call(app, "POST", "/lead", body=b"name=" + b"x" * 30 + b"&email=e", headers=FORM)
    assert res["status"] == 422
    assert json.loads(res["body"])["detail"][0]["type"] == "too_long"


async def test_on_invalid_gets_errors_and_typed_values(app, call):
    async def show(request, errors: RequestValidationError):
        return Response(
            {"fields": errors.fields, "typed": {k: str(v) for k, v in errors.values.items()}},
            status_code=422,
        )

    @app.post("/l2", on_invalid=show)
    async def lead(data: Annotated[Lead, Form()]):
        return "created"

    res = await call(app, "POST", "/l2", body=b"name=A&email=ok%40x&age=abc", headers=FORM)
    assert res["status"] == 422
    out = json.loads(res["body"])
    assert set(out["fields"]) == {"name", "age"}
    assert out["typed"]["email"] == "ok@x" and out["typed"]["age"] == "abc"
    good = await call(app, "POST", "/l2", body=b"name=Ada&email=e", headers=FORM)
    assert good["status"] == 200 and good["body"] == "created"


async def test_on_invalid_template_escapes_typed_values(workdir, app, call):
    (workdir / "templates").mkdir(exist_ok=True)
    (workdir / "templates" / "lead.html").write_text(
        "<input name=email value='{{ values.email }}'>{% for m in errors.name %}<b>{{ m }}</b>{% endfor %}"
    )
    from ushka import render

    async def show(request, errors: RequestValidationError):
        html = await render(request, "lead.html", {"errors": errors.fields, "values": errors.values})
        return Response(html, status_code=422)

    @app.post("/l3", on_invalid=show)
    async def lead(data: Annotated[Lead, Form()]):
        return "created"

    payload = b"name=A&email=%27%3E%3Cscript%3Ealert(1)%3C%2Fscript%3E"
    res = await call(app, "POST", "/l3", body=payload, headers=FORM)
    assert res["status"] == 422
    assert "<script>" not in res["body"]
    assert "<b>" in res["body"]


async def test_on_invalid_decorator_for_file_routes(app, call):
    async def show(errors: RequestValidationError):
        return {"n": len(errors.errors)}, 422

    @app.post("/l4")
    @on_invalid(show)
    async def lead(data: Annotated[Lead, Form()]):
        return "created"

    res = await call(app, "POST", "/l4", body=b"", headers=FORM)
    assert res["status"] == 422 and json.loads(res["body"])["n"] >= 2
