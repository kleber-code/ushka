# ushka verify

Attack your own app and see what got through:

```console
$ ushka verify app:app
◆ Ushka verify · 5 route(s), 46 hostile request(s)

  10 blocked · 18 stopped by the guard · 17 handled safely · 0 vulnerable · 1 crashed

  Crashed on hostile input
  ! GET /boom  query:q  [junk]
      ZeroDivisionError on hostile input: integer division or modulo by zero

  Stopped by Ushka Guard (safe, but a real visitor would see a 500: sanitise here)
  ! GET /go  query:next
      [USHKA-G003] untrusted query value reached redirect() (open redirect / phishing)
    redirect(safe.url(value, allow=["/"], default="/"))
```

It sends XSS, SQL injection, template injection, path traversal, open redirect,
header injection and junk payloads to every route, and checks the responses.
It exits with status 1 when something got through, so it fits in CI.

## It cannot attack anyone else

`verify` runs **inside your process**, against the app object you name. It takes
no URL and opens no socket, so there is no way to point it at another server.

## What each probe ends as

| Outcome | Meaning |
| --- | --- |
| **blocked** | Refused with a 4xx: [validation](validation.md) (422), a sanitiser, or an HTTP error. |
| **guard** | [Ushka Guard](guard.md) refused it inside your handler. Safe, but a real visitor gets a 500: write the fix shown. |
| **handled** | The request went through and the payload did no harm. |
| **vulnerable** | The payload worked: markup reflected in HTML, a template evaluated, `/etc/passwd` returned, a redirect to another site, an injected header, or a database error leaked. |
| **crash** | The handler raised on hostile input (a bug, and a way to knock a route over). |

It also reports unsafe settings: debug on, the guard or the security headers
turned off, CSRF protection off, and any `POST`/`PUT`/`PATCH`/`DELETE` route
that accepts a cross-site request.

## Which inputs it tries

Path parameters, query parameters and JSON body fields from the handler's
signature, plus every name the handler reads with `request.query.get("name")` or
`request.query["name"]`. For anything it cannot see, name it:
`ushka verify app:app --param q --param page`. Each probe changes one input and
leaves the others valid, so a failure points at the right place.

## Routes that write

Probing runs your real handlers. So by default only `GET` routes are probed, and
a `POST` route is only checked for CSRF (the middleware refuses it before your
code runs). To probe them too, use a **test database**:

```console
$ USHKA_DATABASE_URL=sqlite:///test.db ushka verify app:app --include-writes
```

## Routes exempt from CSRF

Webhooks (Mercado Pago, GitHub, Stripe) and machine APIs are listed in
`[security] csrf_exempt_paths`. They are the routes strangers can call without a
browser, so they are probed like any other, with the **same method rules**: `GET`
always, `POST`/`PUT`/`PATCH`/`DELETE` only with `--include-writes`. The report
says which ones are exempt (`exempt` in `--json`, `(exempt from CSRF)` next to a
finding). `--skip-exempt` leaves them out.

The one probe they do not get is the cross-site CSRF check: an exempt route is
meant to accept a request from another site, so a `200` there is not a finding.
The payload probes carry no cross-site headers, so the CSRF check cannot hide
what they find, and they cannot be blamed on it either.

## Redirects

A redirect is not a finding by itself: a protected route sends you to the login
page. `verify` reports an open redirect only when the `Location` reflects the probe:

| `Location` | Result |
| --- | --- |
| `/login?next=/dashboard` | nothing |
| `/login?next=/dashboard?q=//evil.example` (the probe inside the visitor's own URL) | nothing |
| `//evil.example/x`, `https://evil.example/x` | **high**: the visitor lands on another site |
| `/login?next=//evil.example/x` (the probe *is* the `next` value) | **medium**: an open redirect unless the login page checks `next` |

The body of a redirect is not checked for markup, since a browser never shows it.

## Probing as a logged-in user

Without a session, a protected route only ever answers with a redirect to the
login, so its handler is never attacked. Give `verify` a visitor:

```console
$ USHKA_APP_SECRET_KEY=... ushka verify app:app --as-session uid=1 --as-session role=admin
$ ushka verify app:app --cookie "_ushka_session=..."      # a cookie you already have
```

`--as-session KEY=VALUE` (repeatable; `1` is an integer, `true` a boolean, the rest
text) forges a session signed with the app's secret key and sends it with every
probe, and with `[session] store = "database"` it creates the record in the store
and removes it when the run ends. Only the keys of the session are printed, never
the values. It is a test tool: keep the key in the environment or `.env`, use a
development key and a test database. The same cookie is available to your own
tests as `ushka.sessions.forge_session_cookie` (see
[Sessions](sessions.md#forging-a-session-for-tests)) and to `curl` as
[`ushka session`](cli.md#ushka-session).

## Options

| Option | |
| --- | --- |
| `--include-writes` | Also probe `POST`, `PUT`, `PATCH` and `DELETE` routes. |
| `--skip-exempt` | Leave out the routes exempt from CSRF (they are probed by default). |
| `--as-session KEY=VALUE` | Probe as a logged-in user: forge a session with this item (repeatable). |
| `--cookie NAME=VALUE` | Send this cookie with every probe. |
| `--param NAME` | Also probe this query parameter (repeatable). |
| `--json` | Print the report as JSON. |
| `--fail-on high\|medium\|none` | Lowest severity that makes the exit status 1. Default `medium`: vulnerabilities and crashes fail, guard refusals do not. |

Startup and shutdown hooks run around the probes, like under a server.
Hostile input is a good test but not a proof: it finds what these payloads
find, so keep reviewing code that builds HTML, SQL or paths.
