# 📤 Producing Responses: How Your App Talks Back! 💬

Sending a response back to the client is the grand finale of handling a request. Ushka makes this surprisingly flexible, whether you need a quick JSON blast or total micromanagement over headers and status codes. Minimal fuss, maximum control.

## 🤖 Automatic Responses: Let Ushka Do the Work!

For most everyday scenarios, you don't even need to bother creating a `Response` object yourself. Ushka is clever enough to figure it out based on what you return from your route function. Convenient, right?

### Returning a Dictionary for JSON: API's Best Friend! 🤝

If your route function returns a Python `dict`, Ushka automatically converts it to a JSON string and slaps on a `Content-Type` header of `application/json`. Easy as pie.

```python
@app.get("/api/user")
def get_user_data():
    return {
        "id": 123,
        "username": "UshkaFan",
        "email": "fan@ushka.dev",
        "status": "awake, probably"
    }
```

This is your bread and butter for building JSON APIs.

### Returning a String for HTML: Good Old Web Pages! 🌐

If you return a plain `str`, Ushka assumes it's HTML and thoughtfully sets the `Content-Type` header to `text/html`.

```python
@app.get("/")
def homepage():
    return "<h1>Welcome to the Ushka Framework! Don't break anything.</h1>"
```

## 🧑‍🔬 Manual Responses: When You Need to Be the Boss!

Sometimes, you crave more power. You want a custom status code, specific response headers, or a different media type. For these moments, you can explicitly create and return a `Response` object. Your wish is Ushka's command.

First, you'll need to import it: `from ushka import Response`.

### Setting Status Codes: Informing the Client! 🚥

The `status_code` argument lets you tell the client exactly what happened with their request.

```python
from ushka import Response

@app.post("/items")
def create_item():
    # ... logic to create item ...
    return Response(
        content='{"status": "created", "message": "Item successfully spawned."}',
        status_code=201,  # 201 Created - Because success deserves a badge
        media_type="application/json"
    )
```

### Adding Custom Headers: Extra Info for the Road! 🛣️

The `headers` argument takes a dictionary of headers. Perfect for, say, custom caching rules or a cheeky "X-Powered-By" header.

```python
@app.get("/custom")
def custom_header():
    return Response(
        content="Check the headers, I dare you!",
        headers={"X-Ushka-Powered-By": "Pure Awesomeness"}
    )
```

### Changing the Media Type: File Formats Galore! 📝

The `media_type` argument directly sets the `Content-Type` header. Useful for serving XML, CSV, or any other media type your heart desires.

```python
@app.get("/sitemap.xml")
def get_sitemap():
    xml_content = '<?xml version="1.0" encoding="UTF-8"?><urlset><url><loc>https://example.com/</loc></url></urlset>'
    return Response(
        content=xml_content,
        media_type="application/xml"
    )
```

### Redirects: "Over Here, Folks!" ➡️

A classic use for manual responses. Set a `3xx` status code and a `Location` header to send the client off to a new URL.

```python
@app.get("/old-page")
def redirect():
    return Response(
        status_code=307,  # 307 Temporary Redirect - Just a temporary forwarding address
        headers={"Location": "/new-and-improved-page"}
    )
```
