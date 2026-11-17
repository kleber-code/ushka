---
description: app.use(Docs("docs")) turns a folder of Markdown into a searchable documentation site with an API reference. The menu comes from the folders.
---

# Ushka Docs

```python
app.use(Docs("docs"))     # from ushka.docs import Docs
```

That is the whole setup: the Markdown in `docs/` is served at `/docs/`, with a menu,
search, a sitemap and breadcrumbs. Needs the extra: `pip install "ushka[docs]"`.
Add `api="myproject"` and the reference is generated from your docstrings.
`Docs("docs").mount(app)` still works and does the same.

## The menu comes from the folders

Nothing to list. `index.md` opens the site, and each folder is a section:

```text
docs/
  index.md              # the first page
  about.md
  01-install.md         # "01-" only orders; it is not in the URL: /docs/install/
  guide/
    index.md            # "# The guide" is the section title and its first page
    routing.md
    02-testing.md
  _drafts/              # starts with _ or .: left out
```

- **Page title:** `title:` in the front matter, else the first `# heading`, else the file name.
- **Order:** `order: 3` in the front matter, else a number prefix (`01-install.md`), else alphabetical, with `index.md` first.
- **Section title:** the `# heading` of the folder's `index.md`, else the folder name (`getting-started` becomes "Getting Started"). Folders are ordered the same way.
- **API reference:** one group per sub-package of `api="myproject"` (the package is found in `src/`, the project folder or the import path). Names starting with `_` are skipped.

```markdown
---
title: Shown in the menu and the tab
order: 3
description: Used for the meta description and search previews.
---
```

Relative links to other `.md` files (with `#anchor`) are rewritten and checked; use the real file names,
prefix included.

## Options

Most sites need none. Pass them as arguments, or put the brand in `docs/docs.toml`
(arguments win over the file):

```toml
# docs/docs.toml
title = "My project"
base_url = "https://example.com"
logo = "/static/logo.png"
og_image = "https://example.com/static/og.png"
links = [["GitHub", "https://github.com/me/project"]]
edit_url = "https://github.com/me/project/edit/main/docs/"
extra_css = ["/static/brand.css"]
```

| Option | What it does |
| --- | --- |
| `Docs(path="docs", url="/docs", title=None, api=None)` | The folder, where it is mounted, the site name, the package to document. |
| `title`, `base_url` | Name in titles; public origin for canonical URLs, Open Graph and `sitemap.xml`. |
| `logo`, `og_image`, `links`, `edit_url`, `extra_css` | Header logo, social preview, header links, "edit this page" prefix, stylesheets after the theme. |
| `home_url`, `cache_control` | Where the logo links to; `Cache-Control` of the pages. |
| `cache` | Where the rendered site is kept (below). `False` turns it off. |
| `nav` | Name of the navigation file (default `nav.toml`). |
| `api_package`, `api_path` | The older form of `api`. |

## Choose the menu yourself

A `docs/nav.toml` replaces the automatic menu (and then `ushka docs check` also reports pages you forgot to list):

```toml
[[section]]
title = ""
pages = ["index.md"]

[[section]]
title = "Guide"
pages = ["guide/install.md", "guide/routing.md"]

[api]
title = "API reference"

[[api.group]]
title = "Core"
description = "The app, the router and configuration."
modules = ["myproject.core.app", "myproject.core.config"]
```

Without `[[api.group]]`, a flat `modules = [...]` list is grouped by sub-package. With nav.toml,
file names and URLs are used as they are (no number prefixes).

## Check and preview

```console
$ ushka docs check docs --api myproject   # exit code 1 on any problem
$ ushka docs serve docs                   # http://127.0.0.1:8001/docs/
```

`check` fails on broken links and anchors, a module that does not exist, two pages with the same URL
and a bad `docs.toml`. Both work with or without `nav.toml`.

## Cache

Rendering costs about a second of CPU, and every worker does it at startup, so the rendered site is
kept in `.cache/` in the app directory and read by later starts. The file is keyed by a hash of the
Markdown, `docs.toml`, `nav.toml`, the documented sources and the renderer, so **it is never stale**. A
place that cannot be written is ignored. Add `.cache/` to `.gitignore`, or pick the file:
`Docs("docs", cache="build/docs.json")`.

Fill it while building a container image and the container only reads it. See
[Deploy](deploy.md#serving-the-docs-of-your-own-project).

## Make it yours

Besides the options, the theme is a set of templates (`docs/layout.html`, `docs/page.html`,
`docs/search.html`): files with the same names in your project's `templates/docs/` replace them.
The default theme keeps text on flat backgrounds, and its colour pairs meet WCAG AA contrast (4.5:1)
in light and dark mode.

| Route | What it serves |
| --- | --- |
| `/docs/` and `/docs/<page>/` | Rendered pages. |
| `/docs/search?q=` | Search. The query arrives as `Untrusted` and is always escaped. |
| `/docs/sitemap.xml` | Every page, when `base_url` is set. |
| `/docs/<file>` | Images and other assets. Markdown sources, `nav.toml`, `docs.toml` and anything starting with `_` or `.` are never served. |
