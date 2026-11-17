# Pieces: plug anything in with `app.use`

```python
app = Ushka()
app.use(Docs("docs"))
app.use(health)          # your own piece, below
```

One verb for every feature. A **piece** is an object with `install(app)`, or a plain
function that takes the app. It registers what it needs with the app's own methods
(`@app.get`, `app.add_middleware`, `app.on_startup`...), so the same two lines
plug in a battery or your code.

## Write one

```python
def health(app):
    @app.get("/health")
    async def ok():
        return "ok"
```

With options, make it a class:

```python
class Audit:
    def __init__(self, log="audit.log"):
        self.log = log

    def install(self, app):
        @app.middleware
        async def record(request, call_next):
            response = await call_next(request)
            open(self.log, "a").write(f"{request.method} {request.path} {response.status_code}\n")
            return response

app.use(Audit(log="/var/log/shop.log"))
```

## Swap one

A piece has a `name` (the one you give it, or its class or function name in lower case),
and the app keeps it in `app.pieces`:

```python
app.pieces["docs"]       # the Docs piece, to read or change
app.use(MyDocs())        # same name: replaces the old one
```

Using the same object twice installs it once. A route you define always wins over a
built-in one, so a piece can offer a default and you can override it.

`app.use` returns the piece (a tuple for several). Anything else raises a `TypeError`
that says what a piece is.
