# 🗺️ Routing: How Ushka Finds Its Way! 🧭

Ushka offers two flexible ways to handle routing: **File-Based Routing** and **Decorator-Based Routing**. You can use either, or mix them in the same project. We're all about options.

## 1. 📂 File-Based Routing: The "Convention Over Configuration" Fanatic!

This is Ushka's default, opinionated approach. Just create a `routes` directory, and Ushka automatically maps your file structure to your API endpoints. It's almost too easy.

The name of the Python file determines the path, and the name of the function inside determines the HTTP method. Simple, yet effective.

### Example Structure: Where Everything Lives! 🏡

```text
my_project/
└── routes/
    ├── index.py        # GET / (The homepage, obviously)
    ├── users.py        # GET /users (For all your user-related business)
    └── items/
        ├── index.py    # GET /items (A list of... items)
        └── [id].py     # GET /items/<id> (Details for a specific item, because we're fancy)
```

### Basic Route: Your First Endpoint! 📍

To create a `GET /` endpoint, just make `routes/index.py`:

```python
# routes/index.py
# This function answers to GET /
def get():
    return "This is the homepage. Try not to get lost."
```

### Dynamic Routes: Paths with Personality! 🌟

Need a route with a dynamic parameter, like `/items/123`? Use square brackets `[]` in the filename. It's a common pattern for a reason.

```python
# routes/items/[id].py
# This function handles GET /items/<id>
def get(id: str):
    return f"You've requested item with ID: {id}. Hope it's worth it."
```
The parameter `id` is automatically injected into your function. We're not making you parse URLs manually.

### Supported HTTP Methods: Just Name It! 🗣️

Simply name your function after the HTTP method in lowercase: `get()`, `post()`, `put()`, `delete()`, etc. Ushka gets it.

```python
# routes/users.py

# Responds to GET /users
def get():
    return "List of users. Please don't ask for their passwords."

# Responds to POST /users
async def post(request: Request):
    user_data = await request.json()
    # ... create user logic ...
    return {"status": "user created", "data": user_data}
```

---

## 2. 🎀 Decorator-Based Routing: Explicit is as Explicit Does!

If you prefer to define your routes explicitly in a single file (like some sort of control freak, just kidding!), you can use decorators. It's a familiar sight for Flask or FastAPI users.

This method is great for smaller applications or for logically grouping routes, completely independent of the file structure. Keep your chaos contained.

### Example: Your Decorator Extravaganza! 🎉

In your main `app.py` file:

```python
from ushka import Ushka, Request

app = Ushka()

@app.get("/")
def index():
    return "<h1>Hello from a decorator! Fancy seeing you here.</h1>"

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return f"Details for user {user_id}. Don't get too nosy."

@app.post("/users")
async def create_user(request: Request):
    user_data = await request.json()
    return {"status": "created", "user": user_data}

if __name__ == "__main__":
    app.run()
```

The path in the decorator supports dynamic parameters using the same `{param}` syntax you've seen elsewhere. These parameters are then injected into your function by name. It's almost too convenient.

---

## 🤔 When to Use Which? (A Little Guidance)

Both routing styles are fantastic, but they shine in different scenarios:

*   **File-Based Routing:**
    *   **Best for:** Larger APIs with a clear, hierarchical structure (e.g., `/api/v1/users/`, `/api/v1/items/`). It keeps your project organized automatically, almost like magic.
    *   **Pros:** Less boilerplate, easy to navigate (just look at your file tree!), encourages modularity.
    *   **Cons:** Can get unwieldy for very complex, non-hierarchical routing logic that spans many files.

*   **Decorator-Based Routing:**
    *   **Best for:** Smaller applications, single-file APIs, or when you want to group a few related routes together in one Python file, regardless of its location in the file system.
    *   **Pros:** All routes are explicitly defined in code, easy to see at a glance, familiar to users of other web frameworks.
    *   **Cons:** Can lead to a single, large file if not managed well, potentially obscuring route definitions if you have many.

Feel free to mix and match! Ushka is flexible enough to let you choose the best approach for each part of your project. 💖