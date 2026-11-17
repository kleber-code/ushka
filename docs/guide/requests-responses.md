# Requests and responses

What a handler receives and what it can return. Routes themselves are in
[Routing](routing.md).

## What a handler can receive

Handlers declare what they need and Ushka passes it in:

- `request`: the current [`Request`](#the-request).
- `response`: a fresh `Response` you can fill and return.
- `config`: the application [configuration](configuration.md).
- Path, query, header, cookie and body parameters, by name and type: see
  [Validation and typed parameters](validation.md).
- `Depends(fn)`: the result of a function, see [Dependency Injection](dependency_injection.md).

## The request

| Attribute | What it is |
| --- | --- |
| `request.method`, `request.path` | `"GET"`, `"/users/42"`. |
| `request.path_params` | The captured path parameters, as a `dict`. |
| `request.query` | Query string as a `dict`. A repeated key (`?tag=a&tag=b`) gives a list. |
| `request.headers` | Headers as a `dict` with **lower-case** names: `request.headers["user-agent"]`. |
| `request.cookies` | Cookies. Also used to set them: see [Sessions and cookies](sessions.md). |
| `request.session` | Signed cookie session (`dict`). Needs a [secret key](configuration.md#the-secret-key). |
| `await request.body()` | Raw body (`bytes`). |
| `await request.text()` | Body decoded as UTF-8. |
| `await request.json()` | Parsed JSON. |
| `await request.form()` | URL-encoded or multipart form fields. |
| `await request.files()` | Uploaded files, see [Uploads](sessions.md#uploads). |
| `request.stream()` | Async iterator over body chunks, for large uploads. |
| `request.app` | The `Ushka` app (for `request.app.config`). |

Invalid JSON, invalid UTF-8 or a malformed form answers **400 Bad Request**; a
body larger than the [`[limits]`](configuration.md#all-settings) answers
**413 Payload Too Large**. You do not need to catch those yourself.

Everything read from the request is [`Untrusted`](guard.md#sources-what-is-untrusted).
Plain text and JSON can carry it freely. The guarded sinks refuse it.

## Return values

Return whatever is most natural; Ushka turns it into a response.

| You return | Response |
| --- | --- |
| `dict`, `list`, `bool`, `float` | JSON (`application/json`). |
| `str` | `text/plain`, or `text/html` when it contains `<html` or `<!DOCTYPE html>`. |
| `bytes` | The bytes as they are. |
| `int` | The number as text. |
| `None` | `204 No Content`. |
| A t-string (Python 3.14+) | HTML with every value escaped. |
| `(body, status)` or `(body, status, headers)` | That body with that status code (and headers). |
| `Response(...)` | Used as is. |

Anything else raises a `TypeError` explaining what is allowed. Text and JSON
get `; charset=utf-8` in their `content-type`, and a body of known size is sent
with `Content-Length`.

```python
# routes/items/index.py
async def post(request):
    data = await request.json()
    if not data.get("name"):
        return {"error": "name is required"}, 400
    return {"created": data["name"]}, 201, {"Location": "/items/1"}
```

For typed bodies that answer 422 on their own, see [Validation](validation.md).

!!! warning "HTML built from request data is refused"
    A string served as HTML that contains an `Untrusted` value raises
    [USHKA-G001](guard.md#ushka-g001). Render a [template](templates.md), return
    a t-string on Python 3.14+, or escape the value with `safe.html()`. As
    `text/plain` or JSON the same value is fine.

## Building a `Response` yourself

```python
from ushka import Response

async def get():
    return Response(
        "id,name\n1,Ada\n",
        status_code=200,
        headers={"Content-Disposition": "attachment; filename=users.csv"},
        media_type="text/csv",
    )
```

`Response(body, status_code=200, headers=None, media_type=None)`. A `dict` or
`list` body becomes JSON. Whatever you set on `response.headers` is sent, and
cookies and the session are saved on it automatically.

## Redirects

```python
from ushka import redirect, safe

async def post(request):
    form = await request.form()
    # ... check the credentials ...
    return redirect(safe.url(form.get("next"), allow=["/"], default="/"))
```

`redirect(to, status_code=302)` also accepts 301, 303, 307 and 308. The target is
a guarded sink: a value from the request is refused with
[USHKA-G003](guard.md#ushka-g003) until `safe.url()` has checked it.

## Errors

Raise `HttpNotFound`, `HTTPForbidden` and friends to answer with an error page,
or return `(body, status)` for a JSON API. See [Error handling](error_handling.md).

## Streaming, SSE and files

- `StreamingResponse` and `EventSourceResponse`: see [WebSockets and Server-Sent Events](realtime.md#server-sent-events).
- Files from disk: [Static files](static_files.md).
