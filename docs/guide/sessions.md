# Sessions and cookies

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

Files have their own page: [Uploads](uploads.md). In short,
`request.files()` returns `UploadFile` objects (and a parameter typed
`UploadFile` receives one), each with `save()`, `read()` and `size`.
