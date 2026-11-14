"""Ushka Docs: a folder of Markdown becomes a documentation site.

    from ushka import Ushka
    from ushka.docs import Docs

    app = Ushka()
    Docs("docs", title="My project", base_url="https://example.com").mount(app)

Pages are rendered once at startup (Markdown, server-side highlighting, API
reference from docstrings) and served with ETags. Search runs on the server.
Every page gets a title, description, canonical URL, Open Graph tags and
breadcrumbs as JSON-LD, and ``/docs/sitemap.xml`` lists them all.

Needs the ``docs`` extra: ``pip install "ushka[docs]"``. The theme lives in
``docs/*.html`` templates; put files with the same names in your project's
``templates/docs/`` to restyle it.
"""

from __future__ import annotations

try:
    import griffe  # noqa: F401
    import markdown_it  # noqa: F401
    import pygments  # noqa: F401
except ImportError as exc:  # pragma: no cover - exercised without the extra
    raise ImportError(
        f"Ushka Docs needs the docs extra (missing: {exc.name}). "
        "Install it with: pip install 'ushka[docs]'"
    ) from exc

from .site import Docs, DocsPage, DocsProblem

__all__ = ["Docs", "DocsPage", "DocsProblem"]
