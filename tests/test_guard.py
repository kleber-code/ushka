"""Ushka Guard: `Untrusted` propagation, sanitisers, sinks and the AST rewrite."""

import ast
import json
import pickle
import sys
from pathlib import Path

import pytest

from ushka.guard import (
    RejectedValueError,
    TEMPLATES_SUPPORTED,
    UnsafeValueError,
    Untrusted,
    is_untrusted,
    llm,
    safe,
    source_of,
    taint_deep,
)
from ushka.guard import rewrite

needs_314 = pytest.mark.skipif(not TEMPLATES_SUPPORTED, reason="t-strings need Python 3.14+")

U = Untrusted("Ab<x>", "query:q")


# --- propagation ------------------------------------------------------------

PROPAGATES = {
    "add": lambda u: u + "x",
    "radd": lambda u: "x" + u,
    "mul": lambda u: u * 2,
    "rmul": lambda u: 2 * u,
    "mod (untrusted template)": lambda u: Untrusted("%s!", "q") % "a",
    "rmod (single value)": lambda u: "<%s>" % u,
    "slice": lambda u: u[1:],
    "index": lambda u: u[0],
    "upper": lambda u: u.upper(),
    "strip": lambda u: u.strip(),
    "replace": lambda u: u.replace("A", "B"),
    "split": lambda u: u.split("<")[1],
    "partition": lambda u: u.partition("<")[2],
    "join on untrusted": lambda u: u.join(["a", "b"]),
    "format on untrusted": lambda u: u.format(),
    "single-part f-string": lambda u: f"{u}",
    "iteration": lambda u: next(iter(u)),
}


@pytest.mark.parametrize("op", PROPAGATES.values(), ids=PROPAGATES.keys())
def test_operations_keep_the_mark(op):
    result = op(U)
    assert is_untrusted(result)
    assert source_of(result) in ("query:q", "q")


# Documented gaps of plain Python (closed by `rewrite` for routes/ files).
GAPS = {
    "multi-part f-string": lambda u: f"<b>{u}</b>",
    "format on trusted template": lambda u: "Hi {}".format(u),
    "mod with tuple": lambda u: "%s-%s" % (u, u),
    "join on trusted separator": lambda u: ", ".join([u]),
    "str()": lambda u: str(u),
}


@pytest.mark.parametrize("op", GAPS.values(), ids=GAPS.keys())
def test_known_gaps_without_rewrite(op):
    assert not is_untrusted(op(U))


def test_untrusted_behaves_like_str():
    assert U == "Ab<x>"
    assert hash(U) == hash("Ab<x>")
    assert {"Ab<x>": 1}[U] == 1
    assert json.dumps({"a": U}) == '{"a": "Ab<x>"}'
    assert repr(U) == repr("Ab<x>")  # repr must not leak into output
    assert isinstance(U, str)


def test_untrusted_survives_pickle():
    clone = pickle.loads(pickle.dumps(U))
    assert is_untrusted(clone) and clone.source == "query:q"


def test_pathlib_accepts_untrusted():
    # pathlib < 3.13 interns path parts and rejects str subclasses.
    assert str(Path("/srv") / Untrusted("a/b.txt", "p")) == "/srv/a/b.txt"


def test_taint_deep_marks_nested_strings_and_keys():
    data = taint_deep({"k": ["v", {"n": "w"}], "num": 3}, "json")
    key = next(iter(data))
    assert is_untrusted(key)
    assert is_untrusted(data["k"][0]) and is_untrusted(data["k"][1]["n"])
    assert data["num"] == 3 and not is_untrusted(data["num"])


def test_llm_output_is_untrusted():
    reply = llm("<img src=x onerror=alert(1)>", model="claude")
    assert is_untrusted(reply) and reply.source == "llm:claude"


# --- AST rewrite --------------------------------------------------------------


def _run(source, **env):
    code = rewrite.compile_source(source, "<test>")
    namespace = {rewrite.HELPER_NAME: rewrite.helpers, **env}
    exec(code, namespace)
    return namespace


REWRITE_CASES = {
    "f-string": 'r = f"<b>{u}</b>"',
    "f-string with conversion and spec": 'r = f"[{u!r:>12}]"',
    "f-string nested spec": 'w = 9\nr = f"[{u:>{w}}]"',
    "format on trusted template": 'r = "Hi {}!".format(u)',
    "format with keyword": 'r = "Hi {name}!".format(name=u)',
    "mod with tuple": 'r = "%s-%s" % (u, 1)',
    "mod with dict": 'r = "%(a)s" % {"a": u}',
    "join on trusted separator": 'r = ", ".join([u, "x"])',
    "join on generator": 'r = "".join(c for c in u)',
    "str()": "r = str(u)",
}


@pytest.mark.parametrize("source", REWRITE_CASES.values(), ids=REWRITE_CASES.keys())
def test_rewrite_closes_the_gaps(source):
    ns = _run(source, u=U)
    assert is_untrusted(ns["r"]), ns["r"]
    # ...and the value is exactly what plain Python would have produced.
    plain_ns = {"u": "Ab<x>"}
    exec(compile(source, "<plain>", "exec"), plain_ns)
    assert ns["r"] == plain_ns["r"]


@pytest.mark.parametrize(
    "source, expected",
    [
        ("r = 7 % 3", 1),
        ('r = b"-".join([b"a", b"b"])', b"a-b"),
        ('r = f"{1 + 1}"', "2"),
        ('r = "{:.2f}".format(3.14159)', "3.14"),
        ('str = lambda x: "shadowed"\nr = str(5)', "shadowed"),
        ('r = str(b"x", "ascii")', "x"),
    ],
)
def test_rewrite_keeps_semantics_for_trusted_values(source, expected):
    ns = _run(source)
    assert ns["r"] == expected
    assert not is_untrusted(ns["r"])


def test_import_hook_rewrites_only_listed_packages(tmp_path, monkeypatch):
    pkg = tmp_path / "guarded_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "views.py").write_text('def page(u):\n    return f"<b>{u}</b>"\n')
    other = tmp_path / "plain_pkg.py"
    other.write_text('def page(u):\n    return f"<b>{u}</b>"\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        rewrite.install(["guarded_pkg"])
        import guarded_pkg.views
        import plain_pkg

        assert is_untrusted(guarded_pkg.views.page(U))
        assert not is_untrusted(plain_pkg.page(U))
        # Rewritten code must never be cached as bytecode.
        assert not list((pkg / "__pycache__").glob("views*.pyc"))
    finally:
        rewrite.uninstall()
        for name in ("guarded_pkg.views", "guarded_pkg", "plain_pkg"):
            sys.modules.pop(name, None)


def test_rewrite_preserves_line_numbers():
    with pytest.raises(ZeroDivisionError) as info:
        _run('x = f"{1}"\n\ny = 1 / 0\n')
    assert info.traceback[-1].lineno + 1 == 3


# --- sanitisers ---------------------------------------------------------------


@pytest.mark.parametrize("target", ["/", "/account", "/a?b=1#c"])
def test_safe_url_accepts_same_site_paths(target):
    assert safe.url(Untrusted(target, "q")) == target
    assert not is_untrusted(safe.url(Untrusted(target, "q")))


@pytest.mark.parametrize(
    "target",
    [
        "//evil.com",
        "/\\evil.com",
        "https://evil.com/",
        "javascript:alert(1)",
        "account",  # relative to the current URL
        "/ok\r\nSet-Cookie: x=1",
        "https://user@pay.example.com/",
        "",
    ],
)
def test_safe_url_rejects_off_site_targets(target):
    with pytest.raises(RejectedValueError):
        safe.url(Untrusted(target, "q"), allow=["/", "https://pay.example.com"])
    assert safe.url(Untrusted(target, "q"), default="/") == "/"


def test_safe_url_accepts_allowed_origin():
    url = "https://Pay.Example.com/checkout"
    assert safe.url(url, allow=["https://pay.example.com"]) == url


def test_safe_path(tmp_path):
    (tmp_path / "pub").mkdir()
    assert safe.path(Untrusted("a.txt", "q"), tmp_path / "pub") == (tmp_path / "pub" / "a.txt").resolve()
    for bad in ["../secret", "/etc/passwd", "a\x00b", ""]:
        with pytest.raises(RejectedValueError):
            safe.path(Untrusted(bad, "q"), tmp_path / "pub")


def test_safe_integer_and_choice():
    assert safe.integer(Untrusted(" 42 ", "q"), min=0, max=100) == 42
    for bad in ["4.2", "abc", "101", True]:
        with pytest.raises(RejectedValueError):
            safe.integer(bad, min=0, max=100)
    options = ["name", "created_at"]
    chosen = safe.choice(Untrusted("name", "q"), options)
    assert chosen is options[0]  # your object, not the client's
    with pytest.raises(RejectedValueError):
        safe.choice(Untrusted("1; DROP TABLE", "q"), options)


def test_safe_html_and_trust():
    escaped = safe.html(Untrusted("<script>", "q"))
    assert str(escaped) == "&lt;script&gt;" and not is_untrusted(escaped)
    with pytest.raises(ValueError):
        safe.trust(U, reason=" ")
    assert not is_untrusted(safe.trust(U, reason="admin-only preview"))


def test_unsafe_error_is_structured_and_log_safe():
    from ushka.guard import check_redirect

    with pytest.raises(UnsafeValueError) as info:
        check_redirect(Untrusted("//x", "query:a\nFAKE LOG LINE"))
    data = info.value.to_dict()
    assert data["code"] == "USHKA-G003" and "safe.url" in data["fix"]
    assert "\n" not in str(info.value)


def test_guard_package_does_not_import_the_rest_of_ushka():
    guard_dir = Path(__file__).resolve().parent.parent / "src" / "ushka" / "guard"
    for file in guard_dir.glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert not (node.module or "").startswith("ushka"), file.name
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith("ushka") for a in node.names), file.name


# --- integration with the framework -------------------------------------------


@pytest.fixture
def debug_app(make_app, workdir):
    (workdir / "ushka.toml").write_text("[app]\ndebug = true\n")
    return make_app()


async def test_request_data_arrives_untrusted(app, call):
    seen = {}

    @app.post("/items/[item_id]")
    async def handler(request, item_id):
        seen["query"] = request.query["q"]
        seen["header"] = request.headers["x-test"]
        seen["cookie"] = request.cookies["c"]
        seen["json"] = (await request.json())["name"]
        seen["path"] = item_id
        return "ok"

    res = await call(
        app,
        "POST",
        "/items/42",
        query=b"q=hello",
        body=b'{"name": "bob"}',
        headers={"x-test": "v", "cookie": "c=1", "content-type": "application/json"},
    )
    assert res["status"] == 200
    assert all(is_untrusted(v) for v in seen.values()), seen
    assert seen["path"].source == "path:item_id"


async def test_redirect_refuses_query_value(debug_app, call):
    from ushka.http.redirect import redirect

    @debug_app.get("/login")
    async def login(request):
        return redirect(request.query.get("next", "/"))

    res = await call(
        debug_app, "GET", "/login", query=b"next=//evil.com", headers={"accept": "application/json"}
    )
    assert res["status"] == 500
    body = json.loads(res["body"])
    assert body["code"] == "USHKA-G003" and body["source"] == "query:next"


async def test_redirect_with_safe_url(app, call):
    from ushka.http.redirect import redirect

    @app.get("/login")
    async def login(request):
        return redirect(safe.url(request.query.get("next"), allow=["/"], default="/"))

    ok = await call(app, "GET", "/login", query=b"next=/home")
    assert ok["status"] == 302 and ok["headers"]["location"] == "/home"
    evil = await call(app, "GET", "/login", query=b"next=//evil.com")
    assert evil["headers"]["location"] == "/"


async def test_rejected_value_is_400(app, call):
    @app.get("/page")
    async def page(request):
        return str(safe.integer(request.query.get("n")))

    assert (await call(app, "GET", "/page", query=b"n=abc"))["status"] == 400
    assert (await call(app, "GET", "/page", query=b"n=3"))["body"] == "3"


async def test_untrusted_html_body_is_blocked_but_plain_text_is_fine(app, call):
    @app.get("/hi")
    async def hi(request):
        return "<html><h1>" + request.query["name"] + "</h1></html>"

    @app.get("/echo")
    async def echo(request):
        return request.query["name"]

    blocked = await call(app, "GET", "/hi", query=b"name=%3Cscript%3Ealert(1337)")
    assert blocked["status"] == 500 and "<script>alert(1337)" not in blocked["body"]
    plain = await call(app, "GET", "/echo", query=b"name=%3Cscript%3Ealert(1337)")
    assert plain["status"] == 200 and plain["headers"]["content-type"] == "text/plain; charset=utf-8"


async def test_fstring_in_routes_file_is_caught(make_app, workdir, call):
    (workdir / "routes").mkdir()
    (workdir / "routes" / "hello.py").write_text(
        "async def get(request):\n"
        '    name = request.query["name"]\n'
        '    return f"<!DOCTYPE html><h1>Hello {name}</h1>"\n'
    )
    app = make_app()
    res = await call(app, "GET", "/hello", query=b"name=%3Cscript%3Ealert(1337)")
    assert res["status"] == 500
    assert "<script>alert(1337)" not in res["body"]


async def test_taint_can_be_disabled(make_app, workdir, call):
    (workdir / "ushka.toml").write_text("[security]\ntaint = false\n")
    app = make_app()
    seen = {}

    @app.get("/x")
    async def x(request):
        seen["q"] = request.query["q"]
        return "ok"

    await call(app, "GET", "/x", query=b"q=1")
    assert not is_untrusted(seen["q"])


def test_jinja_safe_filter_refuses_untrusted():
    from ushka.templating.engine import engine

    template = engine.env.from_string("{{ v|safe }}")
    with pytest.raises(UnsafeValueError):
        template.render(v=Untrusted("<b>", "q"))
    assert template.render(v="<b>") == "<b>"
    assert engine.env.from_string("{{ v }}").render(v=Untrusted("<b>", "q")) == "&lt;b&gt;"


async def test_db_text_refuses_untrusted_sql():
    pytest.importorskip("sqlalchemy")
    from ushka.orm.database import UshkaDB as Database

    with pytest.raises(UnsafeValueError):
        Database.text(Untrusted("SELECT 1; DROP TABLE users", "q"))
    clause = Database.text("SELECT :x", x=Untrusted("1", "q"))
    assert "SELECT :x" in str(clause)


# --- t-strings (Python 3.14+) -------------------------------------------------


@needs_314
def test_tstring_html_escapes_interpolations():
    ns = _run_314(
        "from ushka.guard.templates import html\n"
        'inner = html(t"<i>{x}</i>")\n'
        'r = html(t"<p title=\\"{x}\\">{x} {inner}</p>")\n',
        x=Untrusted('<script>"', "q"),
    )
    assert ns["r"] == (
        '<p title="&lt;script&gt;&#34;">&lt;script&gt;&#34; <i>&lt;script&gt;&#34;</i></p>'
    )


@needs_314
def test_tstring_sql_binds_values():
    ns = _run_314(
        "from ushka.guard.templates import sql\n"
        'r = sql(t"SELECT * FROM users WHERE name = {x} AND id = {n}")\n',
        x=Untrusted("' OR 1=1 --", "q"),
        n=3,
    )
    query, params = ns["r"]
    assert query == "SELECT * FROM users WHERE name = :p0 AND id = :p1"
    assert params == {"p0": "' OR 1=1 --", "p1": 3}


@needs_314
async def test_handler_returning_tstring_is_safe_html(app, call):
    ns = _run_314('async def h(request):\n    return t"<h1>{request.query[\'n\']}</h1>"\n')
    app.router.add_route("GET", "/t", ns["h"])
    res = await call(app, "GET", "/t", query=b"n=%3Cscript%3E")
    assert res["status"] == 200
    assert res["headers"]["content-type"] == "text/html; charset=utf-8"
    assert res["body"] == "<h1>&lt;script&gt;</h1>"


def _run_314(source, **env):
    # Compiled at runtime so this file still parses on Python < 3.14.
    namespace = dict(env)
    exec(compile(source, "<t-string test>", "exec"), namespace)
    return namespace


async def test_orm_insert_works_on_sqlite(tmp_path):
    pytest.importorskip("aiosqlite")
    from ushka.orm.database import UshkaDB

    db = UshkaDB(f"sqlite:///{tmp_path / 't.db'}")

    class Thing(db.Model):
        __tablename__ = "things_guard_test"
        name = db.String(length=20)

    async with db.engine.begin() as conn:
        await conn.run_sync(db.metadata.create_all, tables=[Thing.__table__])
    first = await Thing.create(name="a")
    second = await Thing.create(name="b")
    assert (first.id, second.id) == (1, 2)
    await db.engine.dispose()
