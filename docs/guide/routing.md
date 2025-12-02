# My Routing Shenanigans: How I Find My Way Around (¬‿¬)

So, you want to know how I manage to get your requests to the right place? It's a bit of a dance, darling, and I have two signature moves: **File-Based Routing** and **Decorator-Based Routing**. You can use either, or both, because I'm not a dictator. I just offer superior options.

## 1. File-Based Routing: My Intuitive Mind-Reading

This is my preferred method. It's so intuitive, it's almost like I'm reading your mind. You just create a `routes` directory, and I magically (it's not magic, it's superior engineering) map your file structure directly to your API endpoints. Less coding, more basking in my brilliance.

The name of your Python file? That's your path. The name of the function inside? That's your HTTP method. See? Simple. Elegant. Perfect.

### The Sacred Scrolls: Your Project's Layout

```text
my_project/
└── routes/
    ├── index.py        # My grand entrance: GET /
    ├── users.py        # All your user-related business: GET /users
    └── items/
        ├── index.py    # A list of... well, items: GET /items
        └── [id].py     # Details for a specific item. Because I'm fancy: GET /items/<id>
```

### Your First Command: A Route (UwU)

Want to create a `GET /` endpoint? Just conjure up `routes/index.py` and write:

```python
# routes/index.py
# This little spell responds to GET /
def get():
    return "Welcome to my domain. Try not to break anything."
```

### Dynamic Paths: Because Life Isn't Always Linear

Need a route with a dynamic parameter, like `/items/123`? Just use square brackets `[]` in the filename. It's a rather common pattern, for obvious reasons.

```python
# routes/items/[id].py
# This incantation handles GET /items/<id>
def get(id: str):
    return f"You've summoned item with ID: {id}. Was it worth it?"
```
The `id` parameter? I'll inject it directly into your function. You don't have to get your hands dirty parsing URLs. I'm a service, after all.

### My Repertoire: Supported HTTP Methods

Just name your function after the HTTP method in lowercase: `get()`, `post()`, `put()`, `delete()`, etc. I'll get the hint.

```python
# routes/users.py

# Responds to GET /users
def get():
    return "A list of my loyal subjects. Don't even *think* about their passwords."

# Responds to POST /users
async def post(request: Request):
    user_data = await request.json()
    # ... your arcane user creation rituals go here ...
    return {"status": "user created", "data": user_data}
```

---

## 2. Decorator-Based Routing: When You Want to Be Explicit (and a Little Controlling)

If you're one of those who prefer to define every single route explicitly in one place (I don't judge, much), you can use my trusty decorators. It's a familiar sight for those who've dabbled with other frameworks.

This method is perfect for smaller applications or when you want to group a few related routes together, regardless of where the file lives. Keep your chaos contained, I say.

### Your Grand Showcase: Decorator Style

In your main `app.py` file, you might see something like this:

```python
from ushka import Ushka, Request

app = Ushka()

@app.get("/")
def index():
    return "<h1>Oh, you found me through a decorator! How charming.</h1>"

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return f"Fetching details for user {user_id}. Mind your own business, now."

@app.post("/users")
async def create_user(request: Request):
    user_data = await request.json()
    return {"status": "created", "user": user_data}

if __name__ == "__main__":
    app.run()
```

The paths in my decorators support dynamic parameters using that `{param}` syntax you've seen. And yes, those parameters are then elegantly injected into your function by name. I'm just *too* convenient.

---

## The Eternal Question: Which to Choose? (Spoiler: It's Obvious)

Both my routing styles are, naturally, fantastic. But they do excel in different scenarios. It's like choosing between a laser pointer and a feather toy. Both are fun, but for different kinds of play.

*   **File-Based Routing:**
    *   **Best for:** Larger APIs with a clear, hierarchical structure (e.g., `/api/v1/users/`, `/api/v1/items/`). It keeps your project organized automatically, like a well-trained butler.
    *   **Pros:** Less boilerplate (who needs it?), easy to navigate (just look at your file tree!), encourages modularity (because neatness counts).
    *   **Cons:** Can be a tad overwhelming for truly chaotic routing logic that spans too many files. Don't make me work *too* hard.

*   **Decorator-Based Routing:**
    *   **Best for:** Smaller applications, single-file APIs, or when you want to keep a few related routes in one cozy spot.
    *   **Pros:** All routes are explicitly laid out in code (for the control freaks among us), easy to spot at a glance.
    *   **Cons:** Can lead to a monstrous, single file if you're not careful. Please, for my sake, don't do that.

Feel free to mix and match! I'm flexible enough to let you choose the best approach for each part of your project. After all, I'm here to serve. (¬‿¬)
