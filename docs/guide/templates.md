# Templates

Ushka renders HTML with [Jinja2](https://jinja.palletsprojects.com/). If you
have used Flask or Django templates, you already know the syntax.

## Rendering a template

Templates live in the `templates/` folder **next to your app** (the folder of
the file that creates `Ushka()`), whatever directory you start the server from.

```html
<!-- templates/hello.html -->
<!DOCTYPE html>
<html>
<head><title>Hello from Ushka!</title></head>
<body>
    <h1>Hello, {{ name }}!</h1>
</body>
</html>
```

```python
# routes/greet.py
from ushka.templating import render


async def get(request):
    name = request.query.get("name", "World")
    return await render(request, "hello.html", {"name": name})
```

`render(request, template_name, context=None)` is async and returns the HTML
as a string. `/greet?name=Ada` shows "Hello, Ada!".

`name` came from the query string, so it is `Untrusted`. That is fine here:
templates ending in `.html` or `.xml` are **autoescaped**, so
`?name=<script>` is displayed as text instead of running.

## Always in the context

Besides what you pass, every template receives:

* `request`: the current request (`request.path`, `request.query`,
  `request.app.config.APP_NAME`, ...).
* `messages`: pending [flash messages](flashing.md) as `(category, message)`
  pairs.

## Jinja2 in thirty seconds

```html
{% if user %}
    <p>Welcome back, {{ user.name }}!</p>
{% else %}
    <p>Welcome, guest!</p>
{% endif %}

<ul>
{% for product in products %}
    <li>{{ product.name }}: {{ "%.2f"|format(product.price) }}</li>
{% endfor %}
</ul>
```

Template inheritance works as usual:

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html>
<head><title>{% block title %}My site{% endblock %}</title></head>
<body>{% block content %}{% endblock %}</body>
</html>
```

```html
<!-- templates/products.html -->
{% extends "base.html" %}
{% block title %}Products{% endblock %}
{% block content %}<h1>Products</h1>{% endblock %}
```

## `|safe` and Ushka Guard

`{{ value|safe }}` turns escaping off. On a value from the request that is the
classic way to bring XSS back, so Ushka refuses it with
[USHKA-G002](guard.md#ushka-g002). Use `|safe` only on markup your own code
produced. Note that `safe.html()` from `ushka.guard` returns already escaped
markup, which Jinja2 will not escape a second time.

## Filters, globals and context processors

The template engine is a module-level object you can extend once, at import
time (for example in `app.py`):

```python
# app.py
from datetime import datetime

from ushka import Ushka
from ushka.templating.engine import engine

app = Ushka()

# {{ price|money }}
engine.add_filter("money", lambda value: f"$ {value:,.2f}")

# {{ now().year }}
engine.add_global("now", datetime.now)


# Adds variables to every template. Sync or async; receives the request.
async def site_info(request):
    return {"site_name": request.app.config.APP_NAME, "path": request.path}

engine.add_context_processor(site_info)
```

Now any template can use them:

```html
<footer>{{ site_name }} · © {{ now().year }} · {{ 1234.5|money }}</footer>
```

A context processor returns a `dict` (or `None`). Its values are merged into
the context of every `render()` call *after* your own context, so a key
with the same name replaces the value you passed. Pick names that do not
clash (the built-in processor uses `messages`).

## Overriding built-in pages

When a template is not found in your `templates/` folder, Ushka falls back to
its own templates. That means you can replace a built-in page by creating a
file with the same name; for example `templates/error.html` replaces the error
page. See [Error Handling](error_handling.md#custom-error-pages).

## t-strings (Python 3.14+)

For small snippets you can skip the template file: a handler that returns a
[t-string](guard.md#t-strings-python-314) is served as HTML with every value
escaped.

```python
async def get(request):
    return t"<h1>Hello {request.query.get('name', 'you')}</h1>"
```
