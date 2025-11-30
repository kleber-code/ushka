# Routing

Ushka offers two flexible ways to handle routing: **File-Based Routing** and **Decorator-Based Routing**. You can use one, the other, or mix both in the same project.

## 1. File-Based Routing (Auto-Discovery)

This is the default, convention-over-configuration method. You create a `routes` directory, and Ushka automatically maps the file structure to your API endpoints.

The name of the Python file determines the path, and the name of the function inside determines the HTTP method.

### Example Structure

```text
my_project/
└── routes/
    ├── index.py        # GET /
    ├── users.py        # GET /users
    └── items/
        ├── index.py    # GET /items
        └── [id].py     # GET /items/<id>
```

### Basic Route

To create a `GET /` endpoint, create `routes/index.py`:

```python
# routes/index.py
def get():
    return "This is the homepage."
```

### Dynamic Routes

To create a route with a dynamic parameter, like `/items/123`, use square brackets `[]` in the filename.

```python
# routes/items/[id].py
def get(id: str):
    return f"You requested item with id: {id}"
```
The parameter `id` is automatically injected into your function.

### Supported HTTP Methods

Simply name your function after the HTTP method in lowercase: `get()`, `post()`, `put()`, `delete()`, etc.

```python
# routes/users.py

# Responds to GET /users
def get():
    return "List of users"

# Responds to POST /users
async def post(request: Request):
    user_data = await request.json()
    # ... create user ...
    return {"status": "user created"}
```

---

## 2. Decorator-Based Routing

If you prefer to define your routes explicitly in a single file, you can use decorators, similar to Flask or FastAPI.

This method is ideal for smaller applications or for grouping related routes in a logical way, independent of the file structure.

### Example

In your main `app.py` file:

```python
from ushka import Ushka, Request

app = Ushka()

@app.get("/")
def index():
    return "<h1>Hello from a decorator!</h1>"

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return f"Details for user {user_id}"

@app.post("/users")
async def create_user(request: Request):
    user_data = await request.json()
    return {"status": "created", "user": user_data}

if __name__ == "__main__":
    app.run()
```

The path in the decorator supports dynamic parameters using the same `{param}` syntax as frameworks like FastAPI. These parameters are injected into your function by name.
