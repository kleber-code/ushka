"""app.use(): the one verb that plugs a piece into the app."""

import pytest


class Counter:
    name = "counter"

    def __init__(self):
        self.installed = 0

    def install(self, app):
        self.installed += 1

        @app.get("/count")
        async def count():
            return {"n": self.installed}


async def test_an_object_with_install_is_plugged_in(app, call):
    piece = Counter()
    assert app.use(piece) is piece
    assert (await call(app, "GET", "/count"))["body"] == '{"n": 1}'
    assert app.pieces["counter"] is piece


async def test_a_function_is_a_piece_too(app, call):
    def health(app):
        @app.get("/health")
        async def ok():
            return "ok"

    assert app.use(health) is health
    assert (await call(app, "GET", "/health"))["body"] == "ok"
    assert "health" in app.pieces


def test_several_pieces_return_a_tuple_in_order(app):
    a, b = Counter(), Counter()
    b.name = "other"
    assert app.use(a, b) == (a, b)
    assert list(app.pieces) == ["counter", "other"]


def test_the_same_object_installs_once(app):
    piece = Counter()
    app.use(piece)
    app.use(piece)
    assert piece.installed == 1


def test_a_piece_with_the_same_name_replaces_the_old_one(app):
    first, second = Counter(), Counter()
    app.use(first)
    app.use(second)
    assert app.pieces["counter"] is second and first.installed == 1 and second.installed == 1


def test_a_name_is_taken_from_the_class_when_there_is_none(app):
    class Cache:
        def install(self, app):
            pass

    app.use(Cache())
    assert "cache" in app.pieces


def test_something_that_is_not_a_piece_says_how_to_make_one(app):
    with pytest.raises(TypeError, match=r"install\(app\) or a function\(app\), got int"):
        app.use(42)
