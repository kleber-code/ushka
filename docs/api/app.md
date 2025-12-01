# 🚀 The `Ushka` Application: Your App's Core! ⚙️

The `Ushka` class is the main entry point for your application. It acts as the central orchestrator, deftly handling routing, middleware, and the entire ASGI lifecycle. Think of it as the brain (or perhaps the heart) of your Ushka project.

## ✨ Initialization: Getting Started!

To begin, simply create an instance of the `Ushka` class. No rocket science involved.

```python
from ushka import Ushka

app = Ushka()
```

Ushka is pretty smart. By default, it'll hunt for an `ushka.toml` file in your project's root to load configurations. If it's feeling lonely (i.e., no file found), it'll create a default one for you on its first run. Convenience, thy name is Ushka.

## 🏃‍♀️ Running the App: Let's Go Live!

The `app.run()` method kicks off the Uvicorn ASGI server. Prepare for launch!

```python
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, log_level="INFO")
```

**Parameters:**

*   `host` (`str`): The IP address the server will bind to. Defaults to `"127.0.0.1"`.
*   `port` (`int`): The port number to listen on. Defaults to `8000`.
*   `log_level` (`str`): The minimum level of logs to display. Options: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, or `"CRITICAL"`. Defaults to `"INFO"`.

(Psst! You can also configure the host and port in your `ushka.toml` file, and `app.run()` will dutifully obey.)

## 🗺️ Route Decorators: Explicit Pathfinding!

While Ushka is well-known for its file-based routing magic, you can also define routes explicitly using decorators. This is handy for smaller apps, or when you prefer keeping related logic grouped in one file, independent of its location.

All common HTTP methods are supported:

*   `@app.get(path)`
*   `@app.post(path)`
*   `@app.put(path)`
*   `@app.delete(path)`
*   `@app.head(path)`

**Example:**

```python
@app.get("/items/{item_id}")
def get_item(item_id: int):
    return {"id": item_id, "name": f"Item {item_id}"} # A very creative name.
```

Paths in decorators can contain dynamic parameters using curly braces `{}`. These parameters are then automatically passed as arguments to your function. It's almost like they know what you want.
