# Static Files

CSS, JavaScript, images and fonts are served by Ushka's built-in static file
server. It is **off by default**; projects created with `ushka new` have it
turned on.

## Turning it on

```toml
# ushka.toml
[static]
enable = true      # default: false
url = "/static"    # URL prefix (default)
dir = "static"     # folder, relative to the app directory or absolute (default)
```

The same settings work as environment variables, e.g. `USHKA_STATIC_ENABLE=true`
(see [Configuration](configuration.md)).

With this in place, `static/css/style.css` is served at `/static/css/style.css`.
A relative `dir` is resolved against the application directory.

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
* Responses carry `cache-control: public, max-age=3600`.
* A missing file, or a directory, answers **404**.
* Requests that try to leave the folder (`/static/../app.py`, encoded variants,
  symlinks pointing outside) are refused with 404. The path is checked with
  `safe.path()` from [Ushka Guard](guard.md).
* `HEAD` requests get the headers without the body.

The static route shows up in `ushka routes list` as
`/static/[path:filename] - GET`.

> **Ushka Tip:** Files are read from disk on every request. That is perfect
> for development and small sites; for heavy traffic, put a CDN or a web
> server such as nginx or Caddy in front of the app for `/static/`.
