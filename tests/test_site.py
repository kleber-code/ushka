"""Smoke test for site/ (ushka.satela.com.br), which runs on this framework."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"


@pytest.fixture
def site_app(monkeypatch):
    monkeypatch.chdir(SITE)
    spec = importlib.util.spec_from_file_location("ushka_site_app", SITE / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


async def test_site_routes(site_app, call):
    home = await call(site_app, "GET", "/")
    assert home["status"] == 200 and "Ushka" in home["body"]
    assert (await call(site_app, "GET", "/healthz"))["status"] == 200
    assert (await call(site_app, "GET", "/s/site.css"))["status"] == 200

    script = await call(site_app, "GET", "/install.sh")
    assert script["status"] == 200 and script["body"].startswith("#!/bin/sh")
    digest = hashlib.sha256((SITE / "install.sh").read_bytes()).hexdigest()
    assert (await call(site_app, "GET", "/install.sh.sha256"))["body"] == f"{digest}  install.sh\n"


async def test_site_error_page_is_the_site_template(site_app, call):
    res = await call(site_app, "GET", "/does-not-exist")
    assert res["status"] == 404 and "This page does not exist" in res["body"]
