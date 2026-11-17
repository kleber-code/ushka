# Quickstart

From nothing to a running, secure app in about five minutes. You need
[Ushka installed](install.md).

## 1. Create the project

```bash
ushka new hello
cd hello
ushka dev
```

Open <http://127.0.0.1:8000>. You see a welcome page, and editing
`routes/index.py` reloads it. `ushka dev` is the development server: it reloads
on change and turns debug on, so errors show a full traceback.

## 2. Add a route

A file in `routes/` is a URL, and a function named after an HTTP verb answers it.
Create `routes/greet/[name].py`:

```python
# routes/greet/[name].py
async def get(name: str):
    return {"hello": name}
```

Visit <http://127.0.0.1:8000/greet/Ada>. The brackets in the file name capture
that part of the URL, and returning a `dict` gives you JSON.

## 3. Type your inputs

Annotations are validation. Add a query parameter with a limit:

```python
# routes/greet/[name].py
from typing import Annotated
from ushka import Query

async def get(name: str, times: Annotated[int, Query(ge=1, le=5)] = 1):
    return {"hello": [name] * times}
```

`/greet/Ada?times=3` works. `/greet/Ada?times=99` answers **422** with every
problem listed. See [Validation](validation.md).

## 4. Meet the guard

Everything from the client is `Untrusted`. Try to put it in HTML:

```python
# routes/page.py
async def get(request):
    name = request.query.get("name", "friend")
    return f"<html><body><h1>Hello {name}</h1></body></html>"
```

Visit `/page?name=Ada`. Ushka refuses it with `USHKA-G001`, in the terminal and
on the debug page, and the message tells you the fix: render a template, return
a t-string (Python 3.14), or escape with `safe.html()`. Use the template that
`ushka new` made:

```python
# routes/page.py
from ushka import render

async def get(request):
    name = request.query.get("name", "friend")
    return await render(request, "index.html", {"name": name})   # autoescaped
```

That is Ushka's idea in one example: the unsafe version does not run silently.
[Ushka Guard](guard.md) covers the rest.

## 5. Check and attack your own app

```bash
ushka routes list          # what is registered
ushka check                # settings and security checks
ushka verify app:app       # sends hostile payloads to your own routes
```

## 6. Run it for real

```bash
ushka check --production   # fails on debug on, a missing secret...
ushka run                  # the production server
```

[Deploy](deploy.md) shows a Dockerfile and the settings to set.

## Prefer one file?

```python
# app.py
from ushka import Ushka

app = Ushka()

@app.get("/greet/[name]")
async def greet(name: str):
    return {"hello": name}

if __name__ == "__main__":
    app.run()
```

## Where to go next

- [Project structure](project-structure.md): what each file is for.
- [Routing](routing.md) and [Requests and responses](requests-responses.md).
- [Build a small API](tutorial_simple_api.md) step by step.
