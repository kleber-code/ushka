# Benchmarks

A small, reproducible load test: Ushka against Starlette and FastAPI, each as a
single uvicorn worker (h11, no uvloop) with the same three routes.

```console
$ export PYTHON=.venv/bin/python        # a venv with ushka, starlette, fastapi
$ ./run.sh ushka ushka_app
$ ./run.sh ushka-no-security ushka_app USHKA_SECURITY_HEADERS=false USHKA_SECURITY_CSRF=false
$ ./run.sh starlette starlette_app
$ ./run.sh fastapi fastapi_app
```

`run.sh` pins the server to CPU 2 and the load generator (`load.py`, 4 processes
x 32 keep-alive connections) to CPUs 4-7, so they do not compete. It needs at
least 8 logical CPUs and `taskset` (Linux). Routes: `GET /` (a tiny JSON),
`GET /items/42?q=abc` (typed path and query), `POST /items` (JSON body into a
dataclass or pydantic model).

Read the numbers with care: one laptop, a hello-world workload, and variation
between runs of 10% or more. Use medians of several rounds, and compare ratios,
not absolute values. A real app spends its time in your code and database, not here.
