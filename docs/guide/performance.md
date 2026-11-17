# Performance

Ushka is small on purpose, and fast without tuning. This page says what you get
by default, what the numbers are, and how to measure your own app.

## What you get by default

`pip install ushka` installs two compiled packages next to Uvicorn, and Uvicorn
uses them without any configuration:

- **`uvloop`**, a fast event loop written in C, in place of Python's `asyncio` loop.
- **`httptools`**, the HTTP parser behind Node.js, in place of the pure-Python `h11`.

On the project's benchmark, a single worker went from about 3,200 to about
7,600 requests per second on the hello route (about **2.3x**), and the typed and
`POST` routes by 2.6x and 1.7x. They are not installed on Windows or PyPy, where
`uvloop` does not exist; Ushka quietly falls back to `asyncio` and `h11` there.

To compare against the pure-Python stack, run Uvicorn yourself with the slow
choices:

```bash
uvicorn app:app --loop asyncio --http h11
```

## Idle cost

A server that does nothing should cost nothing. Stock Uvicorn wakes every worker
10 times a second and, with several workers, pings each one twice a second.
That adds up to about 1.2 s of CPU per minute for an idle two-worker app.

`ushka run` uses its own server loop (`ushka.core.server`) instead:

- each worker wakes **once a second** (that is all the `Date` header needs);
- the supervisor **sleeps** until a worker dies, a signal arrives or the next health check, which is every 10 seconds;
- a new worker is exempt from pings for **90 seconds**, so an app that takes a while to import is not killed in a loop.

An idle two-worker app measured **0.04 s of CPU per minute**, against 0.32 s with
stock Uvicorn. `ushka dev` still uses plain Uvicorn, because reload needs it.

## Workers

```toml
[server]
workers = 2
```

One worker handles many concurrent requests, since it is async. Add workers for
CPU-bound work or to use more cores, and keep in mind each one costs memory and
startup time. See [Deploy](deploy.md#workers).

## Benchmark

One uvicorn worker on a laptop (12th Gen i5-1235U), Python 3.13, 128 keep-alive
connections, median of 3 rounds, zero errors. Requests per second:

| | hello | typed route | POST + body validation | memory |
| --- | ---: | ---: | ---: | ---: |
| Starlette (no validation) | 9,207 | 8,970 | 6,775 | 31 MB |
| Ushka, security off | 8,335 | 7,376 | 6,305 | 33 MB |
| **Ushka, defaults** | **7,902** | **6,531** | **5,258** | **33 MB** |
| FastAPI | 6,165 | 5,085 | 4,921 | 47 MB |

With every protection on, Ushka does 28% more than FastAPI on the hello route
and the typed route, and 7% more on the validated `POST`. The default security
middleware costs about 5% on hello and up to 17% on the validated `POST`. Bare
Starlette is faster, and validates and protects nothing.

Treat this with care. It is a laptop and a hello-world, run-to-run variation was up
to 35%, and differences under 10% are noise. A real app spends its time in your code
and your database.

## Measure it yourself

The benchmark lives in
[`benchmarks/`](https://github.com/kleber-code/ushka/tree/main/benchmarks) and
compares Ushka, Starlette and FastAPI on the same three routes:

```bash
export PYTHON=.venv/bin/python           # a venv with ushka, starlette, fastapi
cd benchmarks
./run.sh ushka ushka_app                 # defaults (uvloop + httptools)
LOOP=asyncio HTTP=h11 ./run.sh ushka-pure-python ushka_app
./run.sh ushka-no-security ushka_app USHKA_SECURITY_HEADERS=false USHKA_SECURITY_CSRF=false
./run.sh starlette starlette_app
./run.sh fastapi fastapi_app
```

`LOOP` and `HTTP` pick the event loop and parser (`asyncio`/`uvloop` and
`h11`/`httptools`). The script pins the server and the load generator to separate
CPUs and needs `taskset` (Linux) and 8 logical CPUs. Compare **ratios** on your
own machine, not absolute numbers.

To measure your own app, point any load tool (`wrk`, `hey`, `k6`...) at
`ushka run`, never at `ushka dev`, which reloads and has debug on. To check the
idle cost, start `ushka run`, leave it alone, and read the CPU time of its
process after a minute with `ps -o cputime -p <pid>`.

## Tips

- **Profile your handlers first.** The framework is rarely the slow part.
- **Cache static files** with a long `Cache-Control` and fingerprinted names: see
  [Static files](static_files.md#caching).
- **Send small responses with a known size.** Ushka adds `Content-Length` for you,
  which was about 15% faster than chunked encoding on small responses.
- **Do not block the loop.** A synchronous database call or `time.sleep` in an
  `async def` stalls every request on that worker. Use the async [ORM](orm.md) or a thread.
- **Render docs once.** [Deploy](deploy.md#serving-the-docs-of-your-own-project) shows `Docs(cache=...)`.
- **Import less.** `import ushka` takes about 95 ms, and `uvicorn` is only imported when the server starts.
