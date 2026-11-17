"""A missing template variable: tolerant in production, an error you can see in debug."""

from ushka import render

PAGE = "<p>Hello {{ user.name }}!</p>\n<p>{{ missing }}</p>\n"


def _app(make_app, workdir, app_toml=""):
    (workdir / "templates").mkdir(exist_ok=True)
    (workdir / "templates" / "p.html").write_text(PAGE)
    (workdir / "ushka.toml").write_text("[app]\nauto_discover = false\n" + app_toml)
    app = make_app()

    @app.get("/")
    async def home(request):
        return await render(request, "p.html", {"user": {"name": "Ann"}})

    return app


async def test_production_renders_a_missing_variable_as_empty(make_app, workdir, call):
    response = await call(_app(make_app, workdir), "GET", "/")
    assert response["status"] == 200
    assert "<p></p>" in response["body"]


async def test_debug_raises_and_the_error_page_points_at_the_template(make_app, workdir, call):
    response = await call(_app(make_app, workdir, "debug = true\n"), "GET", "/")
    assert response["status"] == 500
    body = response["body"]
    assert "UndefinedError" in body and "&#39;missing&#39; is undefined" in body
    assert "p.html" in body and "line 2" in body  # the template and the line, not just Python frames
    assert "name|default" in body  # and what to do about it


async def test_strict_templates_can_be_turned_on_without_debug(make_app, workdir, call):
    response = await call(_app(make_app, workdir, "strict_templates = true\n"), "GET", "/")
    assert response["status"] == 500
    assert "UndefinedError" not in response["body"]  # production page: nothing leaks


async def test_each_new_app_sets_the_mode_again(make_app, workdir, call):
    # The engine is shared by the process: a debug app must not leave strictness behind.
    from ushka.templating.engine import engine

    _app(make_app, workdir, "debug = true\n")
    assert engine.strict
    _app(make_app, workdir)
    assert not engine.strict
    assert engine.env.undefined.__name__ == "Undefined"


async def test_framework_pages_render_in_strict_mode(make_app, workdir, call):
    app = _app(make_app, workdir, "debug = true\n")
    response = await call(app, "GET", "/nowhere")
    assert response["status"] == 404
    assert "UndefinedError" not in response["body"]


async def test_the_welcome_page_renders_in_strict_mode(make_app, workdir, call):
    (workdir / "ushka.toml").write_text("[app]\nauto_discover = false\ndebug = true\n")
    response = await call(make_app(), "GET", "/")
    assert response["status"] == 200 and "UndefinedError" not in response["body"]
