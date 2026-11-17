# Error Handling

Ushka turns every error into a proper HTTP response: expected errors (404,
400, ...) get an error page with the right status code, and unexpected
exceptions become a 500 that shows details only in debug mode.

## What happens by default

| Situation | Status |
| --- | --- |
| No route matches the path | 404 Not Found |
| The path exists, but not for this method | 405 Method Not Allowed, with an `Allow` header |
| Invalid JSON, UTF-8, query string or form data | 400 Bad Request |
| A sanitiser rejects a value (`RejectedValueError`) | 400 Bad Request |
| A typed parameter or body does not [validate](validation.md) | 422 Unprocessable Entity, with every problem in JSON |
| A cross-site write, or a wrong `Origin` ([security middleware](security.md)) | 403 Forbidden |
| `Host` not in `allowed_hosts` | 400 Bad Request |
| Body larger than the [`[limits]`](settings.md) | 413 Payload Too Large |
| Missing static file | 404 Not Found |
| Any other exception, including `UnsafeValueError` from [Ushka Guard](guard.md) | 500 Internal Server Error |

Error pages are rendered with the `error.html` template (validation errors are JSON).

## Redirecting from anywhere

`raise HTTPRedirect(url, status_code=302)` is `return redirect(url, ...)` for
code that cannot return a response, such as a helper or a dependency:

```python
from ushka import HTTPRedirect

def require_login(request):
    if "user" not in request.session:
        request.session["next"] = request.path
        raise HTTPRedirect("/login")
```

Cookies, session values and flash messages set before the `raise` are saved
with the redirect, exactly as with `redirect()`. In general the session and
cookies are saved on every response, including 4xx errors, **only if the handler
changed them**; an unexpected exception (500) saves nothing, so a crash never
half-applies what the handler had done. The URL is checked like `redirect()`:
an `Untrusted` one raises `UnsafeValueError` (use `safe.url()` first).

## Answering from anywhere

`raise HTTPResponse(response)` stops the request with any response, as it is and
without an error page, for example a JSON 401 from a dependency:

```python
from ushka import HTTPResponse, Response

async def api_key(request):
    if request.headers.get("x-api-key") != KEY:
        raise HTTPResponse(Response({"error": "no key"}, status_code=401))
```

To redirect, prefer `HTTPRedirect`: it also saves the session and flash messages.

## Debug mode

With `[app] debug = true` (which `ushka dev` turns on for you):

* a 500 shows a debug page with the exception, the traceback, the code around
  each frame and its local variables (names containing `password`, `secret`,
  `token`, `key`, `auth`, `credential`, `pass` or `cookie` are redacted);
* a 404 lists the routes the app knows about;
* an `UnsafeValueError` requested with `Accept: application/json` comes back as
  JSON with the error `code`, the `risk` and the `fix`, so a coding agent can
  correct the code ([details](guard.md#errors-for-humans-and-for-agents)).

With debug off (the default, and what you want in production) the client only
sees a generic "Internal Server Error" page. The full traceback always goes to
the log.

!!! danger
    Never run production with debug on: the debug page shows source code and
    local variables to anyone. `ushka run` warns about it and
    `ushka check --production` fails.

## Raising HTTP errors

Raise an exception from `ushka.http.exceptions` to stop the request and answer
with an error page:

```python
# routes/posts/[post_id].py
from ushka import render
from ushka.http.exceptions import HttpNotFound

from models import Post


async def get(request, post_id: int):
    post = await Post.get(post_id)
    if post is None:
        raise HttpNotFound(message="Sorry, we couldn't find that post.")
    return await render(request, "post.html", {"post": post})
```

| Class | Default status and message |
| --- | --- |
| `HTTPError` | 400, "Bad Request". The base class: pass any `status_code`. |
| `HttpNotFound` | 404, "Not Found" |
| `HTTPBadRequest` | 400, "Bad Request" |
| `HTTPPayloadTooLarge` | 413, "Payload Too Large" |
| `HTTPMethodNotAllowed` | 405, "Method Not Allowed"; takes `allowed=[...]` for the `Allow` header. |
| `HTTPForbidden` | 403, "Forbidden" |
| `HTTPStaticServerNotFound` | 404, "Static File Not Found" |

They all accept `template`, `status_code` and `message`. **Pass them as
keywords**: the first positional argument is the template name, so
`HttpNotFound("Post not found")` would look for a template called
"Post not found".

For a status without its own class (410 Gone, say), use `HTTPError`:

```python
from ushka.http.exceptions import HTTPError


async def get(request):
    raise HTTPError(status_code=410, message="This page is gone.")
```

To answer with an error *without* an HTML page (in a JSON API, for example),
return a tuple instead of raising:

```python
return {"error": "not found"}, 404
```

## Custom error pages

Ushka looks up templates in your `templates/` folder before its own, so to
replace the built-in error page create `templates/error.html`. It receives:

| Variable | Value |
| --- | --- |
| `status_code` | `404`, `500`, ... |
| `message` | The exception's `message`. |
| `timestamp` | A `datetime` of when the error happened. |
| `available_urls` | In debug mode, for HTTP errors: `(path, methods)` pairs. Empty otherwise. |
| `request` | The current request. |

```html
<!-- templates/error.html -->
<!DOCTYPE html>
<html>
<head><title>{{ status_code }} · {{ message }}</title></head>
<body>
  {% if status_code == 404 %}
    <h1>Oops! Page not found</h1>
    <p>We couldn't find the page you were looking for.</p>
  {% else %}
    <h1>{{ status_code }}</h1>
    <p>{{ message }}</p>
  {% endif %}
  <a href="/">Go back home</a>
</body>
</html>
```

The same template serves every status, including the production 500 page;
branch on `status_code` for different designs. The debug page
(`debug_error.html`) is only used in debug mode.

There is no automatic `404.html` or `500.html`. To use a different template
for one error, pass it when you raise:

```python
raise HttpNotFound(template="post_missing.html", message="That post is gone.")
```
