# Sessions, cookies and uploads

## Sessions

`request.session` is a `dict` that survives between requests. Ushka stores it in
a **signed cookie** (HMAC-SHA256 with a timestamp), so there is no server-side
store to run.

```python
# routes/visits.py
async def get(request):
    request.session["visits"] = request.session.get("visits", 0) + 1
    return {"visits": request.session["visits"]}
```

It is saved on whatever response you return. Things to know:

- **It needs a secret key.** `ushka new` writes `USHKA_APP_SECRET_KEY` to `.env`.
  Debug mode makes a throwaway key; production without one raises a `RuntimeError`
  that says how to create it. See [the secret key](configuration.md#the-secret-key).
- **Signed, not encrypted.** The client can read the contents, but cannot change
  them. Never store a secret in the session.
- **About 4 KB.** It lives in a cookie. Store an id and keep the data in a database.
- **Lifetime.** Fourteen days by default, `HttpOnly` and `SameSite=Lax`, and
  `Secure` whenever debug is off, so browsers send it over **HTTPS** only.
- **Values come back as plain strings.** Data you stored is not `Untrusted` when
  you read it back, so do not store raw client input and later put it in HTML
  without escaping.
- To log a user out, call `request.session.clear()`.

[Flash messages](flashing.md) are built on the session.

## Cookies

Read cookies from `request.cookies` (they are `Untrusted`) and set them there too:

```python
async def post(request):
    theme = request.cookies.get("theme", "light")
    request.cookies.set("theme", "dark", max_age=3600)
    request.cookies.delete("old_cookie")
    return {"was": theme}
```

`set(key, value, max_age=None, expires=None, path="/", domain=None, secure=None,
httponly=None, samesite=None)`. New cookies are `HttpOnly`, `SameSite=Lax` and
`Secure` (unless debug is on), which is the safe default. A cookie holds client
data, so treat it like a query parameter.

To read one as a typed parameter use `Cookie()`: see [Validation](validation.md).

## Uploads

Send a `multipart/form-data` form and read the files with `request.files()`:

```python
# routes/avatar.py
from pathlib import Path
from ushka.guard import safe

UPLOADS = Path("uploads")

async def post(request):
    upload = (await request.files())["avatar"]      # filename, content_type, file
    name = Path(upload["filename"]).name
    target = safe.path(name, root=UPLOADS, default=None)   # stays inside UPLOADS
    if target is None:
        return {"error": "bad file name"}, 400
    UPLOADS.mkdir(exist_ok=True)
    target.write_bytes(upload["file"].read())
    return {"saved": name, "type": upload["content_type"]}, 201
```

Each file is a dict with `filename`, `content_type` and `file` (a spooled
temporary file: up to 2 MB stays in memory, the rest goes to disk). Other form
fields are in `await request.form()`.

- **Limits.** `[limits] max_request_body_multipart_size_in_KB` (50 MB) caps each
  uploaded file, and `max_request_body_size_in_KB` (2 MB) caps ordinary bodies
  and the part of a file kept in memory. Beyond them the client gets **413**.
- **The file name is client data.** It is `Untrusted`, and it can contain `../`.
  Build the path with `safe.path()`, as above, or generate your own name.
- **The content type is a claim.** Do not trust it. Check the bytes if it matters.
- **Do not serve uploads from `routes/`.** Put them in a folder and expose it
  with [`app.mount_static`](static_files.md#serving-any-folder), or hand them out
  through a route that checks permissions.
