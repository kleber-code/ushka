"""redirect("/projects/{id}/", id=value): request data in a redirect, as encoded parts."""

import pytest

from ushka.guard import UnsafeValueError, Untrusted
from ushka.http import HTTPRedirect, redirect
from ushka.http.urls import build_url


def test_parts_are_percent_encoded_and_cannot_leave_their_segment():
    assert build_url("/projects/{id}/", {"id": 42}) == "/projects/42/"
    assert build_url("/p/{x}", {"x": "a/b"}) == "/p/a%2Fb"
    assert build_url("/p/{x}", {"x": "../../admin"}) == "/p/..%2F..%2Fadmin"
    assert build_url("/p/{x}", {"x": "//evil.example"}) == "/p/%2F%2Fevil.example"
    assert build_url("/p/{x}", {"x": "a?b=c#d"}) == "/p/a%3Fb%3Dc%23d"
    assert build_url("/p/{x}", {"x": "olá"}) == "/p/ol%C3%A1"
    assert build_url("/p/{x}", {"x": "x\r\nSet-Cookie: a=b"}).count("\n") == 0


def test_a_host_value_cannot_become_the_host():
    # even when the template is just "/{x}", a part never starts a protocol-relative URL
    assert build_url("/{x}", {"x": "/evil.example"}) == "/%2Fevil.example"
    assert not build_url("/{x}", {"x": "\\evil.example"}).startswith(("//", "/\\"))


def test_query_is_encoded_and_lists_repeat():
    assert build_url("/search", query={"q": "a&b=c d"}) == "/search?q=a%26b%3Dc%20d"
    assert build_url("/s?x=1", query={"t": ["a", "b"]}) == "/s?x=1&t=a&t=b"


def test_untrusted_parts_are_fine_but_an_untrusted_template_is_not():
    part = Untrusted("//evil.example", "query:next")
    url = build_url("/go/{where}", {"where": part})
    assert url == "/go/%2F%2Fevil.example" and type(url) is str
    with pytest.raises(UnsafeValueError):
        build_url(Untrusted("/x/{a}", "query:t"), {"a": 1})


def test_template_and_values_must_match():
    with pytest.raises(TypeError, match="needs a value"):
        build_url("/p/{id}/")
    with pytest.raises(TypeError, match="no placeholder"):
        build_url("/p/", {"id": 1})


def test_redirect_and_httpredirect_take_parts():
    res = redirect("/projects/{id}/", id=Untrusted("a b", "path:id"), query={"tab": "files"})
    assert res.status_code == 302 and res.headers["Location"] == "/projects/a%20b/?tab=files"
    exc = HTTPRedirect("/u/{name}", 301, name="ana", query={"x": 1})
    assert exc.url == "/u/ana?x=1" and exc.status_code == 301


def test_the_guard_error_now_shows_the_parts_fix():
    with pytest.raises(UnsafeValueError) as err:
        redirect(Untrusted("/projects/7/", "path:pid"))
    assert 'redirect("/projects/{id}/", id=value)' in str(err.value) and "safe.url" in str(err.value)


async def test_route_file_with_a_path_parameter(make_app, workdir, call):
    (workdir / "routes" / "go").mkdir(parents=True)
    (workdir / "routes" / "go" / "[pid].py").write_text(
        'from ushka.http import redirect\n'
        'async def get(request, pid):\n    return redirect("/projects/{id}/", id=pid, query={"from": request.query.get("from", "")})\n'
    )
    (workdir / "routes" / "bad.py").write_text(
        'from ushka.http import redirect\nasync def get(request, ):\n    return redirect(f"/x/{request.query.get(\'a\', \'\')}")\n'
    )
    (workdir / "ushka.toml").write_text("[app]\n")
    app = make_app()
    res = await call(app, "GET", "/go/42", query=b"from=a%26b")
    assert res["status"] == 302 and res["headers"]["location"] == "/projects/42/?from=a%26b"
    assert (await call(app, "GET", "/bad", query=b"a=1"))["status"] == 500  # f-string of client data: refused, with the fix in the log
