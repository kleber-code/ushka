# Application

The `Ushka` class is the main entry point of your application. It acts as the central orchestrator, handling routing, middleware, and the ASGI lifecycle.

## Initialization

To start, create an instance of the `Ushka` class.

```python
from ushka import Ushka

app = Ushka()
```

By default, Ushka will automatically look for a `ushka.toml` file in your project root to load configuration. If it doesn't find one, it will create a default one for you on the first run.

## Running the App

The `app.run()` method starts the Uvicorn ASGI server.

```python
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, log_level="INFO")
```

**Parameters:**

- `host` (str): The IP address to bind the server to. Defaults to `"127.0.0.1"`.
- `port` (int): The port to listen on. Defaults to `8000`.
- `log_level` (str): The minimum level of logs to display. Can be `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, or `"CRITICAL"`. Defaults to `"INFO"`.

The host and port can also be configured in your `ushka.toml` file, which `app.run()` will respect.

## Route Decorators

While Ushka is famous for its file-based routing, you can also define routes explicitly with decorators. This is useful for smaller apps or for keeping related logic in one file.

All common HTTP methods are supported.

- `@app.get(path)`
- `@app.post(path)`
- `@app.put(path)`
- `@app.delete(path)`
- `@app.head(path)`

**Example:**

```python
@app.get("/items/{item_id}")
def get_item(item_id: int):
    return {"id": item_id, "name": f"Item {item_id}"}
```

The path can contain dynamic parameters using curly braces `{}`, which are then passed as arguments to your function.
