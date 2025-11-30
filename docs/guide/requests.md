# Handling Requests

In Ushka, all information about an incoming request is contained within the `Request` object. This guide will show you how to access and use that information in your routes.

To get access to the `Request` object, simply add it as a type-hinted parameter to your route function. Ushka's dependency injector will handle the rest.

```python
from ushka import Request

def my_route(request: Request):
    ...
```

## Query Parameters

Query parameters are key-value pairs that appear at the end of a URL. For a URL like `/search?q=ushka&page=2`, you can access them via `request.query`.

**`request.query`** is a dictionary.

```python
# GET /search?q=ushka&page=2

@app.get("/search")
def search(request: Request):
    query_term = request.query.get("q", "default")
    page = int(request.query.get("page", 1))
    return f"You searched for '{query_term}' on page {page}."
```

## Request Body

For `POST`, `PUT`, and `PATCH` requests, you'll often need to read the request body. Since reading the body is an I/O operation, the methods to access it are `async`.

### Reading JSON

This is the most common case for APIs. Use `await request.json()`.

```python
# POST /items
# Body: {"name": "New Item", "price": 19.99}

@app.post("/items")
async def create_item(request: Request):
    data = await request.json()
    item_name = data.get("name")
    return {"message": f"Created item: {item_name}"}
```

### Reading Raw Text or Bytes

If you need the raw body, you can use `await request.text()` or `await request.body()`.

```python
# POST /raw
# Body: Any text content

@app.post("/raw")
async def handle_raw(request: Request):
    text_content = await request.text()
    byte_content = await request.body
    return f"Received {len(byte_content)} bytes."
```

### Reading Form Data

For standard HTML forms submitted with `application/x-www-form-urlencoded`, use `await request.form()`.

```python
# POST /login
# Body: username=john&password=secret

@app.post("/login")
async def login(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    return f"Welcome, {username}!"
```

## Request Headers

You can access all request headers through the `request.headers` dictionary-like object. Header keys are case-insensitive.

```python
@app.get("/headers")
def get_headers(request: Request):
    user_agent = request.headers.get("user-agent", "Unknown")
    accept_language = request.headers.get("accept-language")
    return f"Your User-Agent is: {user_agent}"
```
