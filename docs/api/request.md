# Request

The `Request` object holds all information about an incoming HTTP request. To use it, simply type-hint it in your route function, and Ushka's dependency injection system will provide it.

```python
from ushka import Ushka, Request

app = Ushka()

@app.post("/items")
async def create_item(request: Request):
    # You can now access all request data
    headers = request.headers
    data = await request.json()
    return {"message": f"Received item with headers: {headers} and data: {data}"}
```

## Accessing Request Data

Most request data is accessed via properties. For data that requires I/O (like the request body), you'll need to use `await`.

### `request.method`

The HTTP method of the request (e.g., `"GET"`, `"POST"`).

- **Type:** `str`

### `request.path`

The full path of the request.

- **Type:** `str`

### `request.headers`

A case-insensitive, dictionary-like object containing all request headers.

- **Type:** `Dict[str, str]`
- **Example:** `request.headers.get('user-agent')`

### `request.query`

A dictionary containing the query parameters from the URL.

- **Type:** `Dict[str, Any]`
- **Example:** For a URL `/items?id=123&category=books`, `request.query` would be `{'id': '123', 'category': 'books'}`.

### `await request.body`

The raw request body.

- **Type:** `bytes`
- **Note:** This can only be read once.

### `await request.text`

The request body, decoded as a string.

- **Type:** `str`

### `await request.json()`

The request body, parsed as a JSON object. If parsing fails, it will raise an exception.

- **Type:** `Any` (typically `dict` or `list`)

### `await request.form()`

The request body, parsed as a form (URL-encoded).

- **Type:** `Dict[str, Any]`
- **Note:** This is suitable for `application/x-www-form-urlencoded` data. For multipart forms (file uploads), support is planned.
