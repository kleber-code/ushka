# 📥 The `Request` Object: Your App's Incoming Mail! 📧

The `Request` object is your direct line to all information about an incoming HTTP request. To use it, simply type-hint it in your route function, and Ushka's dependency injection system will hand it over. Easy as pie.

```python
from ushka import Ushka, Request

app = Ushka()

@app.post("/items")
async def create_item(request: Request):
    # What did they send us this time?
    headers = request.headers
    data = await request.json()
    return {"message": f"Received data with headers: {headers} and data: {data}. Fascinating."}
```

## 🕵️ Accessing Request Data: What's Inside?

Most request data is accessed directly via properties. For data that requires I/O (like the request body), you'll need to use `await`. Because waiting is part of the process.

### `request.method`: The Verb of the Request! 🗣️

The HTTP method of the request (e.g., `"GET"`, `"POST"`). Just the basics.

*   **Type:** `str`

### `request.path`: Where They're Headed! 🗺️

The full path of the request. No detours here.

*   **Type:** `str`

### `request.headers`: The Metadata Envelope! 📜

A case-insensitive, dictionary-like object containing all request headers. Very polite about capitalization.

*   **Type:** `Dict[str, str]`
*   **Example:** `request.headers.get('user-agent')` to know who's knocking.

### `request.query`: The URL's Attachments! 📎

A dictionary containing the query parameters from the URL. Perfect for filtering and sorting.

*   **Type:** `Dict[str, Any]`
*   **Example:** For `/items?id=123&category=books`, `request.query` would be `{'id': '123', 'category': 'books'}`. Shocking, I know.

### `await request.body`: The Raw Stuff! 📦

The raw, unprocessed request body. Handle with care, it's a one-time read.

*   **Type:** `bytes`
*   **Note:** This can only be read once. So, if you need it, make sure you really need it.

### `await request.text`: Body as a String! 📝

The request body, thoughtfully decoded as a string.

*   **Type:** `str`

### `await request.json()`: The JSON Payload! 📄

The request body, parsed as a JSON object. If it's not valid JSON, an exception will politely inform you.

*   **Type:** `Any` (typically `dict` or `list`)

### `await request.form()`: Old-School Form Data! 📮

The request body, parsed as URL-encoded form data. Great for traditional HTML forms.

*   **Type:** `Dict[str, Any]`
*   **Note:** This is for `application/x-www-form-urlencoded`. Multipart forms (file uploads) are still on the "coming soon" list.
