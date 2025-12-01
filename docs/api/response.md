# 📤 The `Response` Object: How Your App Replies! 💬

While Ushka is smart enough to turn a simple `dict` or `str` from your route into a proper HTTP response, you also have the option to construct a `Response` object manually. This gives you total control over status code, headers, and content type. Minimal overhead, maximum flexibility.

## 🤖 Automatic Responses: The Easy Button!

For most common scenarios, you don't need to manually craft a `Response` object. Ushka will handle it for you based on what your route function returns. Convenient, right?

### Returning a Dictionary: JSON by Default! 🧪

If your route function returns a Python `dict`, Ushka automatically converts it to a JSON string, sets the `200 OK` status, and uses `application/json` as the media type. Perfect for APIs.

```python
@app.get("/user")
def get_user():
    return {"id": 1, "name": "Captain Fluffernutter"} # -> Responds with JSON
```

### Returning a String: Hello HTML! 🌐

If you return a `str`, Ushka assumes it's HTML. It will set a `200 OK` status and a `text/html` media type.

```python
@app.get("/")
def home():
    return "<h1>Welcome Home! Now get to work.</h1>" # -> Responds with HTML
```

## 🧑‍🔬 Manual `Response` Object: When You Need More Power!

For those times when you need fine-grained control (e.g., custom status codes, specific headers, different media types), you can import and return a `Response` object.

### `Response()`: Constructor Details! ⚙️

The `Response` constructor gives you full command.

```python
from ushka import Response

@app.get("/teapot")
def teapot():
    return Response(
        content="I'm a little teapot, short and stout. This is not a real error. Probably.",
        status_code=418, # Yes, 418 is a real HTTP status code. Look it up.
        media_type="text/plain",
        headers={"X-Tea-Type": "Earl Grey"}
    )
```

**Constructor Parameters:**

*   `content` (Union[`str`, `bytes`]): The actual body of the response.
*   `status_code` (`int`): The HTTP status code. Defaults to `200`.
*   `headers` (`Dict[str, str]`): A dictionary of custom response headers.
*   `media_type` (`str`): The media type (MIME type) of the response, like `text/plain`, `application/json`, or `text/html`.

### Redirects: "Go That Way!" ➡️

A common reason to use a manual `Response` is for redirection. This involves setting a 3xx status code and a `Location` header.

```python
@app.get("/old-path")
def redirect_to_new():
    return Response(
        status_code=307,  # 307 Temporary Redirect - For when you move things around
        headers={"Location": "/new-and-improved-path"}
    )
```
