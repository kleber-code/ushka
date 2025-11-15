# Ushka

[![PyPI Version](https://img.shields.io/pypi/v/ushka)](https://pypi.org/project/ushka/)
![Python Versions](https://img.shields.io/pypi/pyversions/ushka)
![License](https://img.shields.io/pypi/l/ushka)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Build](https://img.shields.io/github/actions/workflow/status/kleber-code/ushka/python-publish.yml?branch=main)](https://github.com/kleber-code/ushka/actions)

Ushka is a minimal, experimental Python ASGI web framework based on file-based routing.

## ⚠️ Alpha Stage: Not Production Ready

This is an **early alpha release**. The project is in active, unstable development. The API may change at any time.

## Core Concept: File-Based Routing

The filesystem is the API. Ushka scans a `routes/` directory and maps the file and directory structure directly to URL paths.

*   A file like `routes/hello.py` becomes the endpoint `/hello`.
*   A file named `routes/index.py` becomes the root endpoint `/`.
*   Nested directories become nested paths. `routes/api/v1/status.py` becomes `/api/v1/status`.
*   Dynamic paths are created using square brackets in the filename. `routes/users/[id].py` becomes the endpoint `/users/[id]`.
*   The HTTP method is determined by the function name inside the file (e.g., `get()`, `post()`).

---

## Example

This example uses **autodiscovery** to create a simple API.

### Project Structure

```
examples/
├── app.py
└── routes/
    ├── hello.py
    ├── index.py
    └── hello/
        └── [name].py
```

### 1. The Route Handlers (`examples/routes/`)

These files contain the functions that will handle requests.

**`examples/routes/index.py`** (handles `GET /`)
```python
def get():
    return "Welcome to the autodiscovered example!"
```

**`examples/routes/hello.py`** (handles `GET /hello`)
```python
def get():
    return "Hello, World!"
```

**`examples/routes/hello/[name].py`** (handles `GET /hello/[name]`)
```python
def get(name: str):
    return f"Hello, {name}!"
```

### 2. The Main Application (`examples/app.py`)

This file creates the Ushka application and tells it to automatically discover the routes.

```python
from ushka import Ushka
from pathlib import Path

app = Ushka()

if __name__ == "__main__":
    print("Starting Ushka server on http://127.0.0.1:8000")
    app.run("127.0.0.1", 8000)
```

### How to Run the Example

1.  **Navigate to the project root.**
2.  **Run the application:**
    ```bash
    python examples/app.py
    ```
3.  **Test the routes in your browser or with `curl`:**
    *   `curl http://127.0.0.1:8000/`
    *   `curl http://127.0.0.1:8000/hello`
    *   `curl http://127.0.0.1:8000/hello/Developer`

---

## Manual Routing

For more complex scenarios, you can add routes manually. This is useful if you prefer not to use file-based routing.

```python
from ushka import Ushka

app = Ushka()

def my_handler():
    return "This was added manually."

app.router.add_route("GET", "/manual", my_handler)
```

## Roadmap

1.  **Stabilize and Enhance the Router:** Improve the routing system and its features.
2.  **Request/Response Objects:** Implement robust `Request` and `Response` objects.
3.  **Middleware:** Add support for middleware.
4.  **CLI:** Create a simple CLI for project scaffolding.
5.  **Dependency Injection:** Explore a simple DI system.
