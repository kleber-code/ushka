"""Ushka Guard on Starlette, FastAPI and Django (each skipped when not installed)."""

import enum
from typing import Literal

import pytest

from ushka.guard import UnsafeValueError, is_untrusted

urlpatterns: list = []  # the Django ROOT_URLCONF for these tests is this module


# -- Starlette ---------------------------------------------------------------------------


@pytest.fixture
def starlette_guard():
    pytest.importorskip("starlette")
    pytest.importorskip("httpx")
    from ushka.guard.integrations import starlette as guard

    guard.install()
    yield guard
    guard.uninstall()


def _starlette_client(routes):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    return TestClient(Starlette(routes=routes), raise_server_exceptions=False, cookies={"c": "v"})


def test_starlette_request_data_is_untrusted(starlette_guard):
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def info(request):
        body = await request.json() if request.method == "POST" else {}
        return JSONResponse({
            "query": is_untrusted(request.query_params.get("q")),
            "query_list": all(map(is_untrusted, request.query_params.getlist("q"))),
            "header": is_untrusted(request.headers.get("user-agent")),
            "cookie": is_untrusted(request.cookies.get("c")),
            "path": is_untrusted(request.path_params["pid"]),
            "json": is_untrusted(body.get("k")),
        })

    res = _starlette_client([Route("/i/{pid}", info, methods=["GET", "POST"])]).post("/i/7?q=1&q=2", json={"k": "v"})
    assert res.json() == {"query": True, "query_list": True, "header": True, "cookie": True, "path": True, "json": True}


def test_starlette_form_is_untrusted(starlette_guard):
    pytest.importorskip("multipart")
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def form(request):
        return PlainTextResponse(str(is_untrusted((await request.form()).get("a"))))

    assert _starlette_client([Route("/f", form, methods=["POST"])]).post("/f", data={"a": "1"}).text == "True"


def test_starlette_sinks_refuse_untrusted(starlette_guard):
    from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
    from starlette.routing import Route

    async def html(request):
        return HTMLResponse(request.query_params["v"])

    async def text(request):
        return PlainTextResponse(request.query_params["v"])  # plain text is fine

    async def go(request):
        return RedirectResponse(request.query_params["v"])

    async def file(request):
        return FileResponse(request.query_params["v"])

    client = _starlette_client([Route("/html", html), Route("/text", text), Route("/go", go), Route("/file", file)])
    assert client.get("/html?v=<script>1</script>").status_code == 500
    assert client.get("/text?v=<script>1</script>").status_code == 200
    assert client.get("/go?v=//evil.example", follow_redirects=False).status_code == 500
    assert client.get("/file?v=../../etc/passwd").status_code == 500


def test_starlette_safe_use_still_works(starlette_guard):
    from starlette.responses import HTMLResponse, RedirectResponse
    from starlette.routing import Route

    from ushka.guard import safe

    async def html(request):
        return HTMLResponse(safe.html(request.query_params["v"]))

    async def go(request):
        return RedirectResponse(safe.url(request.query_params["v"], allow=["/"], default="/"))

    client = _starlette_client([Route("/html", html), Route("/go", go)])
    assert "&lt;script&gt;" in client.get("/html?v=<script>").text
    assert client.get("/go?v=//evil.example", follow_redirects=False).headers["location"] == "/"


def test_starlette_uninstall_restores_everything():
    pytest.importorskip("starlette")
    from starlette.responses import HTMLResponse

    from ushka.guard import taint
    from ushka.guard.integrations import starlette as guard

    original = HTMLResponse.__init__
    guard.install()
    assert HTMLResponse.__init__ is not original
    with pytest.raises(UnsafeValueError):
        HTMLResponse(taint("<b>", "query:x"))
    guard.uninstall()
    assert HTMLResponse.__init__ is original
    HTMLResponse(taint("<b>", "query:x"))  # no longer refused


def test_install_twice_is_harmless(starlette_guard):
    starlette_guard.install()
    from starlette.responses import HTMLResponse

    from ushka.guard import taint

    with pytest.raises(UnsafeValueError):
        HTMLResponse(taint("<b>"))


# -- FastAPI -----------------------------------------------------------------------------


@pytest.fixture
def fastapi_guard():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from ushka.guard.integrations import fastapi as guard

    guard.install()
    yield guard
    guard.uninstall()


def test_fastapi_parameters_models_and_dependencies_are_untrusted(fastapi_guard):
    from fastapi import Depends, FastAPI, Header
    from fastapi.responses import HTMLResponse
    from fastapi.testclient import TestClient
    from pydantic import BaseModel

    class Color(str, enum.Enum):
        red = "red"

    class Item(BaseModel):
        name: str
        tags: list[str] = []

    def dep(token: str = Header("")):
        return is_untrusted(token)

    app = FastAPI()

    @app.get("/q")
    def q(term: str, n: int = 1, c: Color = Color.red, mode: Literal["a", "b"] = "a", d=Depends(dep)):
        return {"term": is_untrusted(term), "n": type(n) is int, "enum": c is Color.red, "literal_plain": not is_untrusted(mode), "dep": d}

    @app.get("/p/{pid}")
    def p(pid: str):
        return is_untrusted(pid)

    @app.post("/item")
    def item(i: Item):
        return {"name": is_untrusted(i.name), "tag": is_untrusted(i.tags[0])}

    @app.get("/html", response_class=HTMLResponse)
    def html(term: str):
        return HTMLResponse(term)

    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/q?term=a&n=2&c=red&mode=b", headers={"token": "x"}).json() == {"term": True, "n": True, "enum": True, "literal_plain": True, "dep": True}
    assert c.get("/p/abc").json() is True
    assert c.post("/item", json={"name": "x", "tags": ["t"]}).json() == {"name": True, "tag": True}
    assert c.get("/html?term=<script>1</script>").status_code == 500  # without the guard this was 200


def test_fastapi_uninstall_restores(fastapi_guard):
    import fastapi.dependencies.utils as utils

    patched = utils.solve_dependencies
    fastapi_guard.uninstall()
    assert utils.solve_dependencies is not patched
    fastapi_guard.install()


def test_fastapi_install_fails_closed_when_internals_change(monkeypatch):
    pytest.importorskip("fastapi")
    import fastapi.dependencies.utils as utils

    from ushka.guard.integrations import fastapi as guard

    monkeypatch.delattr(utils, "solve_dependencies")
    with pytest.raises(RuntimeError, match="does not support this FastAPI"):
        guard.install()


# -- Django ------------------------------------------------------------------------------


@pytest.fixture
def django_guard():
    pytest.importorskip("django")
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(DEBUG=True, SECRET_KEY="x", ALLOWED_HOSTS=["*"], ROOT_URLCONF=__name__, USE_TZ=True)
        django.setup()
    from ushka.guard.integrations import django as guard

    guard.install()
    yield guard
    guard.uninstall()


def test_django_request_data_is_untrusted(django_guard):
    from django.test import RequestFactory

    seen = {}

    def view(request, pid):
        seen.update(
            get=is_untrusted(request.GET.get("q")),
            getlist=all(map(is_untrusted, request.GET.getlist("q"))),
            post=is_untrusted(request.POST.get("a")),
            cookie=is_untrusted(request.COOKIES.get("c")),
            header=is_untrusted(request.headers.get("User-Agent")),
            path=is_untrusted(pid),
            json=is_untrusted(request.json()["k"]) if request.content_type == "application/json" else None,
        )
        from django.http import HttpResponse

        return HttpResponse("ok", content_type="text/plain")

    mw = django_guard.GuardMiddleware(lambda r: view(r, **kwargs))
    rf = RequestFactory()

    def run(request):
        nonlocal kwargs
        kwargs = {"pid": "7"}
        mw.process_view(request, view, (), kwargs)
        mw.get_response = lambda r: view(r, **kwargs)
        return mw(request)

    kwargs = {}
    request = rf.post("/x/7?q=1&q=2", {"a": "1"}, HTTP_USER_AGENT="t")
    request.COOKIES["c"] = "v"
    run(request)
    assert seen == {"get": True, "getlist": True, "post": True, "cookie": True, "header": True, "path": True, "json": None}

    seen.clear()
    request = rf.post("/x/7", '{"k": "v"}', content_type="application/json")
    run(request)
    assert seen["json"] is True


def test_django_sinks_refuse_untrusted(django_guard):
    from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
    from django.shortcuts import redirect
    from django.utils.safestring import mark_safe

    from ushka.guard import taint

    attack = taint("<script>1</script>", "query:q")
    with pytest.raises(UnsafeValueError):
        HttpResponse(attack)
    with pytest.raises(UnsafeValueError):
        HttpResponseRedirect(taint("//evil.example", "query:next"))
    with pytest.raises(UnsafeValueError):
        redirect(taint("//evil.example", "query:next"))
    with pytest.raises(UnsafeValueError):
        mark_safe(attack)  # what the |safe filter calls

    assert HttpResponse(attack, content_type="text/plain").status_code == 200  # not markup
    assert HttpResponse("<b>mine</b>").status_code == 200
    assert JsonResponse({"q": attack}).status_code == 200
    assert HttpResponseRedirect("/ok").status_code == 302


def test_django_safe_use_still_works(django_guard):
    from django.http import HttpResponse, HttpResponseRedirect

    from ushka.guard import safe, taint

    assert b"&lt;" in HttpResponse(safe.html(taint("<b>"))).content
    assert HttpResponseRedirect(safe.url(taint("//evil.example"), allow=["/"], default="/")).url == "/"


def test_django_uninstall_restores():
    pytest.importorskip("django")
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(DEBUG=True, SECRET_KEY="x", ALLOWED_HOSTS=["*"], USE_TZ=True)
        django.setup()
    from django.http import HttpResponse

    from ushka.guard import taint
    from ushka.guard.integrations import django as guard

    original = HttpResponse.__init__
    guard.install()
    guard.uninstall()
    assert HttpResponse.__init__ is original
    HttpResponse(taint("<b>"))
