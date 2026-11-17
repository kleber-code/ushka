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
  that says how to create it. See [the secret key](configuration.md#env-and-secrets).
- **Signed, not encrypted, unless you ask.** By default the client can read the
  contents, but cannot change them, so never store a secret (a token, a password,
  personal data) in it. Set `[session] encrypt = true` and the cookie becomes a Fernet
  token the client can neither read nor change (needs `ushka[crypto]`; see
  [Encryption](crypto.md#encrypted-session-cookies)). When the session must also be
  revocable, use [server-side sessions](#server-side-sessions): the cookie then holds
  only a random id.
- **About 4 KB.** It lives in a cookie. Store an id and keep the data in a database.
- **Lifetime.** Fourteen days by default, `HttpOnly` and `SameSite=Lax`, and
  `Secure` whenever debug is off, so browsers send it over **HTTPS** only.
- **Values come back as plain strings.** Data you stored is not `Untrusted` when
  you read it back, so do not store raw client input and later put it in HTML
  without escaping.
- To log a user out, call `request.session.clear()`. With a signed cookie this only
  clears the browser's copy; a copied cookie still works until it expires. For a
  logout that really ends the session, use [server-side sessions](#server-side-sessions).

[Flash messages](flashing.md) are built on the session.

## Server-side sessions

```python
app.use(Sessions("database"))
```

A signed cookie cannot be revoked and holds about 4 KB. With a server-side store the cookie carries
only a random id, signed with the secret key; the data stays on the server. It is **off by default**.

`Sessions(store, **options)`: the first argument is `"cookie"` (default) or `"database"`; the rest are
the keys of `[session]`, which `ushka.toml` and the environment still override:

```python
app.use(Sessions("database", idle_timeout=1800))   # end the session after 30 idle minutes
app.use(Sessions("cookie", encrypt=True))          # needs ushka[crypto]
```

```toml
# ushka.toml: the same thing, per environment
[session]
store = "database"      # "cookie" (default) or "database"
max_age = 1209600       # absolute lifetime, in seconds (0 = no limit)
idle_timeout = 1800     # end the session after 30 idle minutes (0 = off)
user_key = "user_id"    # the session key that holds the user id
```

Your routes do not change: `request.session` is still a `dict`. What you gain:

```python
async def login(request):
    request.session["user_id"] = user.id   # first login on an id also rotates it
    request.session.rotate()               # or rotate explicitly, against fixation
    return {"ok": True}

async def logout(request):
    request.session.revoke()               # same as clear(): the record is deleted
    return {"ok": True}

from ushka.sessions.stores import revoke_user_sessions

async def change_password(request):
    ...
    await revoke_user_sessions(request, request.session["user_id"])   # every device
```

- **Logout is real.** `revoke()` / `clear()` deletes the record and expires the
  cookie. A cookie copied before that is worthless.
- **Rotation.** `rotate()` gives the session a new id and keeps its data. Setting
  the `user_key` on a session that did not have it (the login) rotates by itself,
  so an id planted before login cannot be used afterwards.
- **Revoke all of a user.** `await revoke_user_sessions(app_or_request, user_id)`
  deletes every session whose `user_key` value is `user_id` and returns how many.
- **Expiry.** `max_age` counts from creation, `idle_timeout` from the last
  request (renewed at most once a minute, so it is not a write per request).
- **No size limit** other than your store's. Values must be JSON serializable;
  the error names the keys, never the values.
- **Safe at rest.** The id is `secrets.token_urlsafe(32)`, checked with a
  constant-time comparison, and the store keeps only its SHA-256, so a leaked
  database does not hand out working sessions. Cookie flags are as above.
- **It needs a database.** `"database"` uses `[database] url` (or `DATABASE_URL`)
  and creates the table named in `[session] table` on first use. It needs the
  `orm` extra for SQLAlchemy. **Without a configured database, or without
  SQLAlchemy, Ushka keeps using signed cookies** and logs a warning, and
  `ushka check --production` reports it, so you never believe sessions are
  revocable when they are not. There is deliberately no in-memory store: with more
  than one worker it would log people out at random, and a database is shared by
  all of them. Expired rows are removed from time to time.
- **Your own store.** Subclass `SessionStore` (`load`, `save`, `touch`, `delete`,
  `delete_user`, optional `purge`) and assign it: `app.session_store = RedisStore(...)`.
- Reading `request.session` still needs the secret key. Session contents are
  never logged.

## Forging a session for tests

To test a route that needs a logged-in user, do not reach into the internals:

```python
from ushka.sessions import forge_session_cookie, aforge_session_cookie

cookie = forge_session_cookie(app, {"uid": 1, "admin": True})   # "_ushka_session=..."
res = await client.get("/account", headers={"cookie": cookie})

cookie = await aforge_session_cookie(app, {"uid": 1})            # also for store = "database"
```

`forge_session_cookie` signs a cookie with the app's secret key (`app` or its
config; the cookie name follows `[session] cookie_name`). With
`[session] store = "database"` the session lives in the store, so use the
coroutine `aforge_session_cookie`, which creates the record there (in a test
database). `ushka session --set uid=1` prints the same cookie for `curl`, and
`ushka verify --as-session uid=1` probes as that user.

It is a testing tool: whoever can run it can become any user, so keep the key in
the environment or `.env`, and do not run it with the key of a real deployment.
Session values are never logged.

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
