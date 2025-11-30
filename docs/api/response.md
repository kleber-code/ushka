# Response

While Ushka is smart enough to convert a `dict` or `str` from your route into a proper HTTP response, you can construct a `Response` object manually for full control over the status code, headers, and content type.

## Automatic Responses

This is the easiest way to send a response.

### Returning a Dictionary

A `dict` is automatically converted to a JSON response with a `200 OK` status and `application/json` media type.

```python
@app.get("/user")
def get_user():
    return {"id": 1, "name": "John Doe"}  # -> Responds with JSON
```

### Returning a String

A `str` is automatically converted to an HTML response with a `200 OK` status and `text/html` media type.

```python
@app.get("/")
def home():
    return "<h1>Welcome Home</h1>"  # -> Responds with HTML
```

## Manual `Response` Object

For more advanced use cases, import and return a `Response` object.

### `Response()`

The `Response` constructor gives you full control.

```python
from ushka import Response

@app.get("/teapot")
def teapot():
    return Response(
        content="I'm a little teapot",
        status_code=418,
        media_type="text/plain",
        headers={"X-Tea-Type": "Green"}
    )
```

**Constructor Parameters:**

- `content` (Union[str, bytes]): The body of the response.
- `status_code` (int): The HTTP status code. Defaults to `200`.
- `headers` (Dict[str, str]): A dictionary of custom response headers.
- `media_type` (str): The media type (MIME type) of the response, like `text/plain`, `application/json`, or `text/html`.

### Redirects

To perform a redirect, you can use a `Response` with a 3xx status code and a `Location` header.

```python
@app.get("/old-path")
def redirect_to_new():
    return Response(
        status_code=307,  # Temporary Redirect
        headers={"Location": "/new-path"}
    )
```
