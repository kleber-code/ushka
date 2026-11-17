# Sign in with Google and GitHub

```python
app.use(Google(), GitHub())
```

Each provider you use is on, and Ushka serves `/auth/<provider>/login` and `/auth/<provider>/callback`
for it. The credentials come from the environment (`.env` works), the secret only from there:

```bash
USHKA_OAUTH_GOOGLE_CLIENT_ID=1234-abc.apps.googleusercontent.com
USHKA_OAUTH_GOOGLE_CLIENT_SECRET=...        # never in code or ushka.toml
USHKA_OAUTH_REDIRECT_BASE=https://example.com
```

`Google(client_id=None, allowed_domains=None, **options)`; the same for `GitHub`. Give the id in code
if you prefer (`Google(client_id="1234-abc...")`), restrict who may sign in with
`Google(allowed_domains=["example.com"])`, and pass any other key of `[oauth]` as an option
(`after_login="/home"`). A `client_secret` in code is a `TypeError`. `ushka.toml` and the environment win
over code, and the file alone still works:

```toml
[oauth]
google_client_id = "1234-abc.apps.googleusercontent.com"
redirect_base = "https://example.com"
allowed_email_domains = ["example.com"]   # optional
```

Protect pages with one dependency:

```python
from ushka import Depends
from ushka.auth import login_required, login_url, logout

@app.get("/account")
async def account(user=Depends(login_required)):
    return f"Hello {user['name']} ({user['email']})"

@app.get("/logout")
async def bye(request):
    logout(request)
    return "Signed out"
```

In a template, `<a href="{{ login_url('google', next='/account') }}">Sign in</a>` works once you add
`login_url` to your context.

## Google Cloud Console

1. Open [Google Cloud Console](https://console.cloud.google.com/), create or pick a project.
2. **APIs & Services, OAuth consent screen**: choose *External* (or *Internal* for a
   Workspace-only app), fill in the app name and support e-mail, and add the scopes
   `openid`, `.../auth/userinfo.email` and `.../auth/userinfo.profile`. These are the
   only scopes Ushka asks for.
3. **APIs & Services, Credentials, Create credentials, OAuth client ID**, type
   *Web application*.
4. **Authorized redirect URIs**: add exactly `https://your-domain/auth/google/callback`.
   It must match character by character (scheme, host, path, no trailing slash). For
   local work add `http://localhost:8000/auth/google/callback` as well.
5. Copy the client ID to `USHKA_OAUTH_GOOGLE_CLIENT_ID` (or `Google(client_id=...)`) and the secret to
   `USHKA_OAUTH_GOOGLE_CLIENT_SECRET`.

## GitHub

1. **Settings, Developer settings, OAuth Apps, New OAuth App**.
2. **Authorization callback URL**: exactly `https://your-domain/auth/github/callback`.
3. Generate a client secret. Put the id in `USHKA_OAUTH_GITHUB_CLIENT_ID` (or `GitHub(client_id=...)`) and the
   secret in `USHKA_OAUTH_GITHUB_CLIENT_SECRET`.

Ushka asks for `read:user` and `user:email`, and uses the **primary, verified** e-mail.

## The redirect address

The `redirect_uri` sent to the provider is `redirect_base` + `/auth/<provider>/callback`.
It never comes from the `Host` header, which a client can write. Set `redirect_base`
(`USHKA_OAUTH_REDIRECT_BASE`) or the `url` of `Seo`. In debug mode, or when `[security] allowed_hosts` is set, the address of
the request is used when neither is set. Without a trusted address the app refuses to
start (a piece checks at startup, so `Seo(url=...)` may come after it) and `ushka check` says so.

## What happens

1. `/auth/google/login?next=/account` makes a random `state`, a PKCE verifier (S256) and,
   for Google, a `nonce`; keeps them in the session with `next` (checked with
   `safe.url(..., allow=["/"])` before it is stored) and redirects to the provider.
2. The provider sends the browser back to `/auth/google/callback?code=...&state=...`.
3. Ushka removes the stored flow from the session first (a callback works once),
   compares `state` in constant time, trades the code for a token **from the server**
   (the client secret never reaches the browser), checks the `id_token` claims (nonce,
   issuer, audience, expiry) and fetches the profile.
4. The e-mail must be verified and, if `allowed_email_domains` is set, at an allowed
   domain. On Google, an address at a custom domain also needs the Workspace `hd`
   claim to match, since any Google account can use a verified address anywhere.
5. The session gets only `provider`, `sub`, `email`, `name` and `picture` under
   `[oauth] session_key` (default `user`), its id is rotated, and the visitor goes
   to the stored `next` (or `[oauth] after_login`).

Any failure (the user said no, a bad `state`, the provider is down or slow, an unverified
e-mail, a wrong domain) redirects to `[oauth] login_error_path` with a short code,
`/?login_error=denied`. The codes are `denied`, `provider`, `state`, `network`, `token`,
`profile`, `unverified`, `domain` and `config`. Text from the provider is never shown or
logged. Show your own message for the code:

```python
@app.get("/login")
async def login_page(request):
    return await render(request, "login.html", {"error": request.query.get("login_error")})
```

Set `login_error_path = "/login"` to land there.

## The API

| Name | Does |
| --- | --- |
| `current_user(request)` | The profile dict or `None`. |
| `login_required` | `Depends(login_required)`: the profile, or a redirect to the login with `next` set to the current path and query. With several providers it uses the first configured; `login_required_for("github")` picks one. |
| `login_url("google", next="/x")` | The path of the login route, for links and buttons. |
| `logout(request)` | Empties the session; with server-side sessions it is revoked. |

The routes are built in. A route of yours at the same path wins, with no warning, so
you can replace `/auth/google/login` with a page that shows a button first.

## Use server-side sessions

With the default signed-cookie session, the login lives in the browser: you cannot
revoke it before it expires, and a copied cookie keeps working. Set
`[session] store = "database"` ([Sessions](sessions.md)) so that logout and
`revoke_user_sessions` really end a login, and so the session id changes at login.
`ushka check --production` warns when it is still `"cookie"`.

## Map the profile to your user

`sub` is the stable id of the account at that provider; the e-mail can change. Key your
users on `(provider, sub)`:

```python
@app.get("/account")
async def account(user=Depends(login_required)):
    row = await User.first(provider=user["provider"], sub=user["sub"])
    if row is None:
        row = await User.create(provider=user["provider"], sub=user["sub"], email=user["email"])
    return {"id": row.id}
```

Do not merge two providers on the e-mail alone unless you want a GitHub user who
controls a verified address to take over the Google account of the same address.

## Threat model

What Ushka checks for you:

- CSRF on the login: random `state`, tied to the session, compared in constant time, single use, expiring in 10 minutes.
- Stolen or intercepted codes: PKCE (S256) and the client secret on the server.
- Open redirects through `next`: validated before it is stored, never read from the callback.
- Session fixation: the session id is rotated at login (server-side sessions).
- ID token replay: the `nonce` is checked. The token comes straight from the token endpoint over TLS, so its signature is not verified (OpenID Connect Core 3.1.3.7); the profile is read from the `userinfo` endpoint with the access token.
- Unverified or foreign e-mails; hostile providers or networks: TLS verification, timeouts, a size limit on answers, redirects never followed, no provider text echoed.

What you still do:

- Keep the client secrets in the environment and rotate them if they leak.
- Set `allowed_hosts` and serve over https only.
- Decide what a signed-in user may do: signing in proves who they are, not what they may see.
- Use server-side sessions if you need to revoke logins.
- Treat `name` and `picture` as untrusted text (templates escape them).
