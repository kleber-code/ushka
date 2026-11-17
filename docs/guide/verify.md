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

## Options

| Option | |
| --- | --- |
| `--include-writes` | Also probe `POST`, `PUT`, `PATCH` and `DELETE` routes. |
| `--param NAME` | Also probe this query parameter (repeatable). |
| `--header 'NAME: VALUE'` | Send this header with every request (repeatable), for example `Authorization: Bearer ...`. `Host: ...` picks a host in [per-host routes](routing.md). |
| `--cookie NAME=VALUE` | Send this `Cookie`, to attack the routes behind a login as a signed-in user. Use a test account and a test database. |
| `--json` | Print the report as JSON. |
| `--fail-on high\|medium\|none` | Lowest severity that makes the exit status 1. Default `medium`: vulnerabilities and crashes fail, guard refusals do not. |

Startup and shutdown hooks run around the probes, like under a server.
Hostile input is a good test but not a proof: it finds what these payloads
find, so keep reviewing code that builds HTML, SQL or paths.
