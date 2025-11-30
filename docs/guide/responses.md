# Producing Responses

Sending a response back to the client is the final step in handling a request. Ushka provides a simple and flexible way to do this, whether you need a quick JSON response or full control over headers and status codes.

## Automatic Responses (The Easy Way)

For most use cases, you don't need to create a `Response` object yourself. Ushka will do it for you based on what you return from your route function.

### Returning a Dictionary for JSON

If you return a Python `dict`, Ushka automatically converts it to a JSON string and sets the `Content-Type` header to `application/json`.

```python
@app.get("/api/user")
def get_user_data():
    return {
        "id": 123,
        "username": "UshkaFan",
        "email": "fan@ushka.dev",
    }
```

This is the primary way you'll build JSON APIs.

### Returning a String for HTML

If you return a `str`, Ushka assumes it's HTML and sets the `Content-Type` header to `text/html`.

```python
@app.get("/")
def homepage():
    return "<h1>Welcome to the Ushka Framework!</h1>"
```

## Manual Responses (Full Control)

Sometimes you need to set a custom status code, add response headers, or specify a different media type. For these cases, you can create and return a `Response` object.

First, import it: `from ushka import Response`.

### Setting Status Codes

The `status_code` argument lets you set the HTTP status.

```python
from ushka import Response

@app.post("/items")
def create_item():
    # ... logic to create item ...
    return Response(
        content='{"status": "created"}',
        status_code=201,  # 201 Created
        media_type="application/json"
    )
```

### Adding Custom Headers

The `headers` argument takes a dictionary of headers to add to the response.

```python
@app.get("/custom")
def custom_header():
    return Response(
        content="Check the headers!",
        headers={"X-Ushka-Version": "0.2.0"}
    )
```

### Changing the Media Type

The `media_type` argument sets the `Content-Type` header.

```python
@app.get("/sitemap.xml")
def get_sitemap():
    xml_content = '<?xml version="1.0" encoding="UTF-8"?><urlset></urlset>'
    return Response(
        content=xml_content,
        media_type="application/xml"
    )
```

### Redirects

A common use case for manual responses is redirection. This is done by setting a `3xx` status code and a `Location` header.

```python
@app.get("/old-page")
def redirect():
    return Response(
        status_code=307,  # Temporary Redirect
        headers={"Location": "/new/page"}
    )
```
