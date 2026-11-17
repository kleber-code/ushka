# Static Files

```python
app.use(Static("public", url="/assets"))     # public/app.css is served at /assets/app.css
```

CSS, JavaScript, images and fonts, with `ETag`/`304`, caching and path checks. `Static()` with no
folder turns on `[static]` (`./static` under `/static`), which `ushka new` already does.

| Argument | Meaning |
| --- | --- |
| `directory` | Folder to serve, relative to the app directory. Omit for the `[static]` folder. |
| `url` | URL prefix. |
| `html=True` | Serve `index.html` for folders and redirect `/guide` to `/guide/` (a static-site build). |
| `cache_control` | Default `public, max-age=3600`; `"public, max-age=31536000, immutable"` for fingerprinted names. |

With a folder, `Static` is [`app.mount_static`](#serving-any-folder), and you can mount as many as
you like. Without one, `url` and `cache_control` are defaults that `ushka.toml` and the
environment can still change:

```toml
# ushka.toml: the same thing, per environment
[static]
enable = true      # default: false
url = "/static"    # URL prefix (default)
dir = "static"     # folder, relative to the app directory or absolute (default)
```

With this, `static/css/style.css` is served at `/static/css/style.css`. The settings also work
as environment variables, e.g. `USHKA_STATIC_ENABLE=true` (see [Configuration](configuration.md)).

## Linking to files

Write the path directly; there is no `url_for` helper.

```html
<!DOCTYPE html>
<html>
<head>
    <title>My Ushka App</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <img src="/static/images/logo.png" alt="Logo">
    <script src="/static/js/app.js"></script>
</body>
</html>
```

If you change `[static] url`, update the links too. To avoid repeating the
prefix you can expose it as a template global:

```python
# app.py
from ushka import Ushka
from ushka.templating.engine import engine

app = Ushka()
engine.add_global("static_url", app.config.STATIC_URL)
```

```html
<link rel="stylesheet" href="{{ static_url }}/css/style.css">
```

## How files are served

* The `content-type` is guessed from the extension
  (`application/octet-stream` when unknown).
* Every file has an `ETag` and a `Last-Modified`. A browser that asks again with
  `If-None-Match` gets **304 Not Modified** and no body.
* `cache-control` is `public, max-age=3600` unless you change `[static] cache_control`.
* `X-Content-Type-Options: nosniff` is sent with every file.
* A missing file, or a directory, answers **404**.
* Requests that try to leave the folder (`/static/../app.py`, encoded variants,
  symlinks pointing outside) are refused with 404. The path is checked with
  `safe.path()` from [Ushka Guard](guard.md).
* `HEAD` requests get the headers without the body.

The static route shows up in `ushka routes list` as
`/static/[path:filename] - GET`.

## Caching

The default hour is a safe middle. For files whose name changes when their
content does (`app.3f9a1c.css`), cache them for a year:

```toml
[static]
enable = true
cache_control = "public, max-age=31536000, immutable"
```

Without fingerprinted names, keep it short, or add a version to the link
(`/static/style.css?v=3`). The Ushka website hashes the file in a template global
so a deploy is never hidden behind a cached stylesheet.

## Serving any folder

`Static("public", url="/assets")` (or `app.mount_static(url, directory)`) serves a folder anywhere,
independently of `[static]`. Use it for uploads, a built front end or a static site:

```python
# app.py
app.use(Static("public", url="/assets"))
app.use(Static(
    "dist", url="/site",
    html=True,                                   # /site/guide/ serves dist/guide/index.html
    cache_control="public, max-age=31536000, immutable",
))
```

`html=True` serves `index.html` for directories and redirects `/site/guide` to
`/site/guide/`, so relative links in static-site output work. Files get the same
`ETag`/`304` handling, and every path is checked with `safe.path()`.

For a single file from a route, `ushka.static.file_response(path, request, cache_control)`
returns a response with the same headers. Validate the path with
[`safe.path()`](guard.md#sanitisers-the-way-out) first.

> **Ushka Tip:** Files are read from disk on every request. That is perfect
> for development and small sites; for heavy traffic, put a CDN or a web
> server such as nginx or Caddy in front of the app for `/static/`.
