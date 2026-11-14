"""ushka.satela.com.br: the Ushka website, served by Ushka itself.

Routes
------
/                 landing page (templates/home.html)
/docs/...         the MkDocs documentation, built into public/docs at image build
/install.sh       the installer script, and /install.sh.sha256 next to it
/llms.txt         map of the docs for AI tools
/healthz          health check for the Satela deploy agent
/s/...            site CSS and images
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path

from ushka import Response, Ushka, render
from ushka.http import HttpNotFound
from ushka.static import file_response

HERE = Path(__file__).resolve().parent
PUBLIC = HERE / "public"
INSTALLER = HERE / "install.sh"
INSTALLER_SHA256 = hashlib.sha256(INSTALLER.read_bytes()).hexdigest()

ASSETS_CACHE = "public, max-age=86400, stale-while-revalidate=604800"
DOCS_CACHE = "public, max-age=600, stale-while-revalidate=86400"

app = Ushka()
app.mount_static("/docs", PUBLIC / "docs", html=True, cache_control=DOCS_CACHE)
app.mount_static("/s", HERE / "static", cache_control=ASSETS_CACHE)


def _volume() -> str:
    major, minor, *_ = version("ushka").split(".")
    return f"{major}.{minor}"


@app.get("/")
async def home(request):
    return await render(
        request,
        "home.html",
        {"volume": _volume(), "version": version("ushka"), "installer_sha256": INSTALLER_SHA256},
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
    path = PUBLIC / "docs" / "llms.txt"
    if not path.is_file():
        raise HttpNotFound()
    return file_response(path, request, DOCS_CACHE)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": version("ushka")}
