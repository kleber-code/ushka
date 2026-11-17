---
description: Ushka Docs turns a folder of Markdown into a fast, searchable documentation site with an API reference, served by your Ushka app.
---

# Ushka Docs

Ushka Docs turns a folder of Markdown into a documentation site served by your
own app. It is the engine behind the docs you are reading.

- **Rendering.** Pages are rendered once at startup (or read from a
  [cache](#cache-the-rendered-site)), with code highlighted on the server by
  Pygments, so the browser runs no JavaScript to colour code.
- **Search.** Search runs on the server: no index file to download.
- **API reference.** The reference is generated from your docstrings (numpy
  style) with griffe.
- **SEO.** Every page gets a title, description, canonical URL, Open Graph
  tags and breadcrumbs, and the site publishes a `sitemap.xml`.
- **Checking.** `ushka docs check` fails on broken links, missing anchors or
  pages left out of the navigation, which makes it a good CI step.

It is an optional battery: nothing loads until you use it.

```console
$ pip install "ushka[docs]"
```

## Mount it

```python
# app.py
from ushka import Ushka
from ushka.docs import Docs

app = Ushka()
Docs(
    "docs",                          # the Markdown folder, next to app.py
    url="/docs",
    title="My project",
    base_url="https://example.com",  # canonical URLs and sitemap.xml
).mount(app)
```

`Docs.mount()` registers these routes:

| Route | What it serves |
| --- | --- |
| `/docs/` and `/docs/<page>/` | Rendered pages. `guide/cli.md` becomes `/docs/guide/cli/`. |
| `/docs/search?q=` | Search results. The query arrives as `Untrusted` and is always escaped. |
| `/docs/sitemap.xml` | Every page, when `base_url` is set. |
| `/docs/<file>` | Images and other assets from the docs folder. Markdown sources and `nav.toml` are never served. |

## Write pages

Write plain Markdown (CommonMark) with tables, task lists, definition lists
and admonitions:

```markdown
!!! tip "Optional title"
    Indented text becomes the body of the box.
```

Use relative links to other `.md` files, with an optional `#anchor`; they are
rewritten to page URLs and checked. Heading ids follow the usual slug rules,
so `### USHKA-G003` becomes `#ushka-g003`.

Front matter is optional:

```markdown
---
title: Shown in the tab and in the navigation
description: Used for the meta description and search previews.
---
```

When a page has no description, the first paragraph long enough to describe
it is used instead.

## Navigation

List the pages in reading order in `docs/nav.toml`:

```toml
[[section]]
title = ""
pages = ["index.md"]

[[section]]
title = "Guide"
pages = ["guide/install.md", "guide/routing.md"]

[api]
title = "API reference"
modules = ["myproject.core", "myproject.utils"]
```

The `[api]` modules are documented when you pass `api_package="myproject"`
(and `api_path="src"` if the package lives there).

A flat `modules` list is grouped by sub-package. To choose the groups, titles and
a one-line description of each yourself, use `[[api.group]]` instead:

```toml
[api]
title = "API reference"

[[api.group]]
title = "Core"
description = "The app, the router and configuration."
modules = ["myproject.core.app", "myproject.core.config"]

[[api.group]]
title = "Utilities"
modules = ["myproject.utils"]
```

The sidebar shows each group as a collapsible section (only the one you are in is
open), `api/` lists every module with its summary, and each module page starts
with an index of its classes and functions. `ushka docs check` reports a module
listed twice, a module that does not exist and a group with no title or modules.

## Check and preview

```console
$ ushka docs check docs --api myproject   # exit code 1 on any problem
$ ushka docs serve docs                   # http://127.0.0.1:8001/docs/
```

## Cache the rendered site

Rendering the pages and the API reference costs about a second of CPU, and every
server worker does it at startup. Give `Docs` a cache file and that cost is paid
once:

```python
Docs("docs", url="/docs", api_package="myproject", cache=".cache/docs.json").mount(app)
```

The first start renders the site and writes the JSON file; later starts read it.
The file is keyed by a hash of the Markdown, the documented sources and the
renderer, so **it is never stale**: edit a page and the next start rebuilds it. A
relative path is resolved against the app directory, and a location that cannot
be written is ignored.

The useful trick is to fill the cache while building a container image, so the
container only reads it. See [Deploy](deploy.md#serving-the-docs-of-your-own-project).
The Ushka website starts in 0.3 s this way, instead of about 1 s of CPU per worker.

## Make it yours

The theme is a set of templates (`docs/layout.html`, `docs/page.html` and
`docs/search.html`). Files with the same names in your project's
`templates/docs/` folder replace them. Smaller tweaks need no templates:

```python
Docs(
    "docs",
    logo="/static/logo.png",
    og_image="https://example.com/static/og.png",
    links=[("GitHub", "https://github.com/me/project")],
    edit_url="https://github.com/me/project/edit/main/docs/",
    extra_css=["/static/brand.css"],
)
```

The default theme keeps text on flat backgrounds, and its colour pairs meet
WCAG AA contrast (4.5:1) in light and dark mode.
