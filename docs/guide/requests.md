# 👂 Handling Requests: What Did They Say?! 🧐

In Ushka, all information about an incoming request lives inside the `Request` object. This guide will show you how to pull out exactly what you need in your route functions. Minimal fuss, maximum data.

To get your hands on the `Request` object, just type-hint it in your function. Ushka's dependency injector will handle the rest. You're welcome.

```python
from ushka import Request

def my_route(request: Request):
    # Now, what did they send us?
    ...
```

## 🔍 Query Parameters: The URL's Little Secrets!

Query parameters are those `key=value` pairs at the end of a URL (e.g., `/search?q=ushka&page=2`). Access them via `request.query`.

**`request.query`** is a dictionary. Treat it like one.

```python
# GET /search?q=ushka&page=2 (Because someone's looking for something)

@app.get("/search")
def search(request: Request):
    query_term = request.query.get("q", "default") # Get 'q', or 'default' if they forgot
    page = int(request.query.get("page", 1))       # Get 'page', convert to int, or default to 1
    return f"You searched for '{query_term}' on page {page}. Hope you found it!"
```

## 📦 Request Body: Unboxing the Payload!

For `POST`, `PUT`, and `PATCH` requests, you'll probably find data in the request body. Since reading this data is an I/O operation, the methods are `async`. So, `await` them.

### Reading JSON: The API Standard! 🧑‍💻

Most APIs send JSON. Use `await request.json()`. If it's not JSON, it'll complain.

```python
# POST /items (They're sending us a new item!)
# Body: {"name": "New Widget", "price": 29.99}

@app.post("/items")
async def create_item(request: Request):
    data = await request.json()
    item_name = data.get("name")
    return {"message": f"Created item: {item_name}. Don't spend it all at once!"}
```

### Reading Raw Text or Bytes: For the Purists! 📜

If you need the raw body, whether as text or bytes, you can use `await request.text()` or `await request.body()`.

```python
# POST /raw (Who knows what they're sending now...)
# Body: Any text content

@app.post("/raw")
async def handle_raw(request: Request):
    text_content = await request.text()
    byte_content = await request.body
    return f"Received {len(byte_content)} bytes of... something. Minimalist, I guess."
```

### Reading Form Data: The Old School Way! 📝

For classic HTML forms using `application/x-www-form-urlencoded`, use `await request.form()`.

```python
# POST /login (Someone's trying to log in!)
# Body: username=john&password=secret

@app.post("/login")
async def login(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    return f"Welcome, {username}! Try not to break anything important."
```

## 🎩 Request Headers: The Meta-Data!

All request headers are accessible through `request.headers`, which acts like a dictionary. It's case-insensitive, because we're not monsters.

```python
@app.get("/headers")
def get_headers(request: Request):
    user_agent = request.headers.get("user-agent", "Mysterious Stranger")
    accept_language = request.headers.get("accept-language") # Because knowing languages is good
    return f"Your User-Agent is: {user_agent}. What an intriguing choice."
```
