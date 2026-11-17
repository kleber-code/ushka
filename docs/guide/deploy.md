# Deploy

Ushka runs anywhere Python runs. This page is the checklist, a Dockerfile, and
what to know about workers, proxies and health checks.

## The checklist

```bash
ushka check --production
```

It fails (exit status 1) when debug is on or the secret key is missing or short,
so put it in your pipeline. By hand, a production app needs:

- `debug = false` (the default). Never ship debug: its error page shows source code.
- A long random secret: `USHKA_APP_SECRET_KEY`, from the environment or your
  platform's secret store, never from `ushka.toml`.
- `allowed_hosts` set to your domains, so a forged `Host` header gets 400.
- HTTPS in front, so the session cookie (which is `Secure`) is sent back.
- A [health check](#health-check) and, if you use the ORM, `ushka db migrate` before the new version starts.

## Running the server

```bash
ushka run                                  # uses [server] in ushka.toml
ushka run --host 0.0.0.0 --port 8080
ushka run myapp.main:application           # another module:attribute
```

`ushka run` is the production server: no reload, debug taken from your
configuration, and `[server] workers` processes. In a container, bind to
`0.0.0.0`. Any ASGI server works too (`app` is a plain ASGI application), but
`ushka run` is the one tuned for Ushka: see [how it idles](performance.md#idle-cost).

`ushka dev` is a different server (reload, debug on) and is **not** for production.

## Configure with environment variables

Every setting has a `USHKA_<SECTION>_<KEY>` variable, which beats `ushka.toml`
and `.env`. That is how you configure a container without baking secrets in:

| Variable | Meaning |
| --- | --- |
| `USHKA_APP_SECRET_KEY` | Signs sessions. **Required** if you use sessions or flash messages. |
| `USHKA_APP_DEBUG` | `false` in production. |
| `USHKA_SERVER_HOST`, `USHKA_SERVER_PORT` | Bind address and port. |
| `USHKA_SERVER_WORKERS` | Number of worker processes. |
| `USHKA_SECURITY_ALLOWED_HOSTS` | Comma-separated hosts: `example.com,www.example.com`. |
| `USHKA_SECURITY_CORS_ORIGINS`, `USHKA_SECURITY_CSRF_TRUSTED_ORIGINS` | Comma-separated origins. |
| `DATABASE_URL` (or `USHKA_DATABASE_URL`) | The database. Plain `postgresql://` URLs work. |
| `USHKA_MCP_TOKEN` | Bearer token for [agent tools](agents.md). |
| `USHKA_SECURITY_TRUSTED_PROXIES` | Comma-separated IPs or CIDRs of your reverse proxies. See [behind a proxy](#behind-a-proxy). |

See [All settings](settings.md).

## Workers

```toml
# ushka.toml
[server]
host = "0.0.0.0"
port = 8000
workers = 2
```

Each worker is a separate process with its own copy of your app in memory, so
more workers means more memory and more startup work. They add throughput for
CPU-bound code, because Python runs one thread of it at a time.

- **Start with one per CPU core**, and fewer if memory is tight. With I/O-bound
  routes (a database, an HTTP call) one worker already handles many requests at
  once, because it is async.
- **Do not keep state in process memory** (a `dict` of sessions, a counter): each
  worker has its own. Use the database or a cache. Sessions are signed cookies, so
  they already work across workers.
- **A worker that dies is replaced at once.** One that is still importing your app
  gets 90 seconds before it is health-checked, so a slow start is not mistaken for
  a hang. After that, every 10 seconds the supervisor pings each worker and
  replaces one that does not answer within 30.
- **Signals.** `SIGTERM` or Ctrl+C stops everything gracefully. `SIGHUP` restarts the
  workers, which reloads your code without changing the port.

The server sleeps when nothing happens: it costs close to zero CPU while idle, and
the details are in [Performance](performance.md).

## Health check

Add a route your platform and `HEALTHCHECK` can call:

```python
# app.py
from importlib.metadata import version

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": version("ushka")}
```

Make it cheap: no database call unless you want the platform to restart the app
when the database is down.

## A Dockerfile

```dockerfile
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so this layer is cached until requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt     # contains: ushka

COPY . .

# Run as a normal user, not root.
RUN useradd --system --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz').status != 200)"
CMD ["ushka", "run", "app:app", "--host", "0.0.0.0"]
```

```bash
docker build -t myapp .
docker run -p 8000:8000 \
  -e USHKA_APP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e USHKA_SECURITY_ALLOWED_HOSTS=example.com \
  myapp
```

Keep `.env` out of the image (add it to `.dockerignore`) and pass secrets as
variables at run time. Run `ushka db migrate` as a release step before starting
the new container, not inside every worker.

## Behind a proxy

Most platforms put a proxy (nginx, Caddy, a load balancer) in front of your
container to end TLS. Two things follow:

- **Say which proxies you trust.** List them in `[security] trusted_proxies`
  (IPs or CIDRs; in Docker, the network's range such as `172.18.0.0/16`, or
  `127.0.0.1` for Caddy on the same machine). Empty, the default, trusts no one:
  `X-Forwarded-*` is ignored and `request.client_ip` is whoever connected.

  ```toml
  [security]
  trusted_proxies = ["127.0.0.1", "10.0.0.0/8"]
  ```

  For a request that arrives from a trusted proxy Ushka reads
  `X-Forwarded-For` from the right, skips your proxies and takes the first
  other address as `request.client_ip`; the left-most entry is never believed,
  because the client writes it. `request.scheme` / `request.is_secure` follow
  `X-Forwarded-Proto` (so HSTS is sent) and `request.host` follows
  `X-Forwarded-Host`, both from the nearest trusted proxy. A malformed header
  falls back to the proxy's address. `ushka check --production` warns when the
  server binds `0.0.0.0` and the list is empty.

  Ushka's server (`ushka run`, `ushka dev`, `app.run()`) starts Uvicorn with
  `proxy_headers=False`, so the headers are read once, by this rule, and
  Uvicorn's own `FORWARDED_ALLOW_IPS` no longer applies. If you start Uvicorn
  yourself, pass `--no-proxy-headers` for the same effect.
- **Set `allowed_hosts`.** The proxy forwards the `Host` header, and Ushka will
  reject any not on your list.

## Serving the docs of your own project

If you use [Ushka Docs](docs.md), rendering the pages and the API reference costs
about a second of CPU, and every worker would do it at startup. Give `Docs` a cache
file and build it **once, in the image**:

```python
# app.py
docs = Docs("docs", url="/docs", cache="docs.cache.json")
docs.mount(app)
```

```dockerfile
COPY docs docs
COPY app.py .
# Import the app once at build time: this renders the docs and writes the cache.
RUN python -c "import app"
```

The cache is keyed by a hash of the Markdown, the documented sources and the
renderer, so it is never stale: change a page and it is rebuilt. If the cache
cannot be written (a read-only filesystem at run time), Ushka renders at startup
as before. The Ushka website does exactly this, and its server starts in 0.3 s
instead of spending about 1 s of CPU per worker.

## The Ushka website as an example

The site you are reading is an Ushka app in `site/`, built from
[`site/Dockerfile`](https://github.com/kleber-code/ushka/blob/main/site/Dockerfile)
with the repository root as the build context:

1. It installs Ushka from the repository (`pip install ".[docs]"`).
2. It copies `docs/` and `site/`, then runs `python -c "import app"` to render the docs into the cache.
3. It runs as a non-root user, has a `HEALTHCHECK` on `/healthz`, and starts `ushka run app:app`.
4. [`site/ushka.toml`](https://github.com/kleber-code/ushka/blob/main/site/ushka.toml) sets `host = "0.0.0.0"`, `debug = false` and `workers = 1`: the site serves cached pages, so one worker is enough, and a second would double the idle memory.
5. The platform pushes a new container on every merge to `main` and calls `/healthz`.

Secrets come from the platform's environment, never from the repository.

## Without Docker

```bash
python -m venv .venv && .venv/bin/pip install ushka
USHKA_APP_SECRET_KEY=... .venv/bin/ushka run --host 127.0.0.1 --port 8000
```

Run it under `systemd` (or your process manager), and put nginx or Caddy in front for TLS.
`Restart=on-failure` is all the supervision it needs.
