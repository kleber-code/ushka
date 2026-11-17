"""ushka.satela.com.br: the Ushka website, served by Ushka itself.

Routes
------
/                 landing page (templates/home.html)
/docs/...         the documentation, rendered by ushka.docs from ../docs
/install.sh       the installer script, and /install.sh.sha256 next to it
/llms.txt         map of the docs for AI tools
/robots.txt, /sitemap.xml
/healthz          health check for the Satela deploy agent
/s/...            site CSS, fonts and images
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path

from ushka import Response, Ushka, render
from ushka.docs import Docs
from ushka.static import file_response
from ushka.templating.engine import engine

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ORIGIN = "https://ushka.satela.com.br"
INSTALLER = HERE / "install.sh"
INSTALLER_SHA256 = hashlib.sha256(INSTALLER.read_bytes()).hexdigest()

STATIC = HERE / "static"


def asset(name: str) -> str:
    """URL of a file in static/ with a content hash, so a new deploy is never
    hidden behind the browser's cached copy of the old CSS."""
    digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]
    return f"/s/{name}?v={digest}"


engine.add_global("asset", asset)

app = Ushka()
app.mount_static("/s", HERE / "static", cache_control="public, max-age=86400, stale-while-revalidate=604800")

# Brand (title, logo, links...) is in ../docs/docs.toml; the menu comes from ../docs/nav.toml.
docs = app.use(
    Docs(
        REPO / "docs",
        api="ushka",
        extra_css=[asset("docs-brand.css")],
        # Rendered once (in the image build) instead of by every worker at startup.
        cache=HERE / ".cache" / "docs.json",
    )
)


def _volume() -> str:
    major, minor, *_ = version("ushka").split(".")
    return f"{major}.{minor}"


@app.get("/")
async def home(request):
    return await render(
        request,
        "home.html",
        {"volume": _volume(), "version": version("ushka"), "installer_sha256": INSTALLER_SHA256, "origin": ORIGIN},
    )


@app.get("/install.sh")
async def installer(request):
    response = file_response(INSTALLER, request, "public, max-age=300")
    response.media_type = "text/x-shellscript"
    return response


@app.get("/install.sh.sha256")
async def installer_checksum():
    return Response(f"{INSTALLER_SHA256}  install.sh\n", headers={"Cache-Control": "public, max-age=300"})


@app.get("/llms.txt")
async def llms(request):
    return file_response(REPO / "docs" / "llms.txt", request, "public, max-age=600")


@app.get("/robots.txt")
async def robots():
    return f"User-agent: *\nAllow: /\nDisallow: /docs/search\nSitemap: {ORIGIN}/sitemap.xml\n"


@app.get("/sitemap.xml")
async def sitemap():
    urls = [f"{ORIGIN}/"] + [f"{ORIGIN}/docs/{u}" for u in docs.order]
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": version("ushka")}
