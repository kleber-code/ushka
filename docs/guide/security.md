# Security middleware

Ushka ships a security middleware that is **on by default**. It wraps every
request, including error pages, and needs no code and no extra dependency.
It covers [Ushka Guard](guard.md)'s other half: the HTTP layer around your routes.

| Protection | Default | Setting |
| --- | --- | --- |
| Security headers | on | `[security] headers` |
| CSRF protection | on | `[security] csrf` |
| Trusted hosts | off until you list hosts | `[security] allowed_hosts` |
| CORS | off until you list origins | `[security] cors_origins` |

## Security headers

Every response gets these, unless your route already set the same header:

| Header | Value |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` (`frame_options`) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` (`referrer_policy`) |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'` (`csp`) |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`, on **https requests only** (`hsts_seconds`, `0` turns it off) |

The default CSP blocks inline scripts and third-party scripts, images and
fonts. The browser blocks them **silently**: the server sees nothing, only the
browser console says "Refused to load...". `ushka check` scans `templates/`
and warns with `file:line` for each `<script src="https://...">`, stylesheet
`<link>` to another site and inline `<script>` (not an error: it is a warning).

To fix it, in order of preference: host the file under `static/`; move inline
code to a `.js` file under `static/`; or allow the CDN by setting `csp` in
`ushka.toml` to your own policy (it **replaces** the default, so repeat what you
keep):

```toml
[security]
csp = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
```

An inline script needs `'unsafe-inline'` in `script-src`, which removes most of
what the CSP protects you from; avoid it. Set `csp = "off"` to send no policy.
`ushka check` stops warning about a host your policy names. Behind a proxy that ends TLS, tell the server which
proxy to trust so Ushka sees `https` (see [Deploy](deploy.md#behind-a-proxy)).

## CSRF

Ushka blocks a state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`) that
a browser sends **from another site**. There is no token to put in your forms
and no secret key to configure. It works from what the browser reports:

- `Sec-Fetch-Site: same-origin` passes. `cross-site` and `same-site` get **403**.
- Without that header, the `Origin` host must equal the `Host`. `Origin: null` gets 403.
- With neither header, the request did not come from a browser (curl, a mobile app, another server) and passes: it cannot be forged through a victim's browser.

To let another site write, list it in `csrf_trusted_origins`. For a webhook
that arrives from a browser-like sender, list the path in `csrf_exempt_paths`.
Origins allowed by CORS are trusted for CSRF too.

## Trusted hosts

A forged `Host` header poisons password-reset links and cache keys. Set the
hosts your app answers to and everything else gets **400**:

```toml
[security]
allowed_hosts = ["example.com", "*.example.com"]
```

In `.env`, write a comma-separated list: `USHKA_SECURITY_ALLOWED_HOSTS=example.com,www.example.com`.

## CORS

Browsers on another origin are refused unless you list it:

```toml
[security]
cors_origins = ["https://app.example.com"]
cors_credentials = true          # let it send cookies
cors_headers = ["content-type"]  # default: echo what the preflight asks for
```

Preflight (`OPTIONS`) requests are answered by the middleware. `cors_origins = ["*"]`
is allowed, but not together with `cors_credentials`: Ushka refuses to start, because
that combination would hand your users' cookies to any website.

## Your own middleware

```python
@app.middleware
async def timing(request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = "ushka"
    return response
```

Middleware runs in the order added, inside the security middleware. Errors
raised downstream arrive as an ordinary `Response` (a 404 page, a 500 page), so
you never need a `try`. To stop a request, return a response instead of
calling `call_next`.
