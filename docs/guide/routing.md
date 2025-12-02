# Routing

Routing is the heart of any web framework. It's the system that connects incoming requests (URLs) to the Python functions that handle them. In Ushka, we've made routing as simple and intuitive as possible.

## Filesystem-Based Routing: The "Aha!" Moment

Imagine your website's URL structure is a map. In many frameworks, you have to draw this map by hand, listing every single route in a configuration file. It's tedious and prone to errors.

Ushka takes a different approach: your filesystem *is* the map.

The structure of your `routes` directory directly translates to your application's URL structure.

*   A file named `routes/index.py` corresponds to the root URL: `/`.
*   A file named `routes/about.py` corresponds to the URL: `/about`.
*   A nested file like `routes/blog/posts.py` corresponds to: `/blog/posts`.

Inside these files, you define functions that handle specific HTTP methods (like GET, POST, etc.).

```python
# In routes/index.py

async def get():
    return {"message": "Welcome to the home page!"}

async def post():
    return {"message": "You've submitted something!"}
```

This is the magic of filesystem-based routing. You don't need a central routing file. Just create a file, define a function, and your route is live.

> **Ushka Tip:** Organizing your project with filesystem-based routing is like tidying up your room. It might seem like a small thing, but it makes it much easier to find things later! Your future self will thank you.

## Dynamic Routes: Capturing a Piece of the URL

Sometimes, you need to create routes that capture a variable part of a URL. For example, you might want a user's profile page to be at `/users/alice` or `/users/bob`. This is where dynamic routes come in.

In Ushka, you create a dynamic route by using square brackets `[]` in your filename or directory name.

Let's say you want to create a route that handles URLs like `/users/[username]`. You would create a file named `routes/users/[username].py`.

The value inside the brackets is then passed as an argument to your handler function.

```python
# In routes/users/[username].py

async def get(username: str):
    return {"message": f"This is the profile page for {username}."}
```

Now, if you visit `/users/charlie`, your function will receive `"charlie"` as the `username` argument.

### Type Hinting for Fun and Profit

Python's type hints are not just for show! They make your code more readable and can help prevent bugs. In Ushka, you should always use type hints for your dynamic route parameters.

```python
# In routes/posts/[id].py

async def get(id: int):
    # Now, `id` is guaranteed to be an integer.
    # If a non-integer is provided in the URL, Ushka will handle it.
    return {"message": f"You are reading post number {id}."}
```

Using `int` will automatically convert the URL part to an integer and provide basic validation.

## Dependency Injection: Your Helpful Assistant

Imagine you're a busy chef in a kitchen. You need ingredients like `request` details, a `response` object to fill, or your application's `config`. Instead of running around to get them yourself, you have an assistant who brings them to you right when you need them.

That's what dependency injection is in Ushka.

If your route handler function includes parameters named `request`, `response`, or `config`, or uses their types (`Request`, `Response`, `Config`), Ushka will automatically provide them for you.

```python
# In routes/search.py
from ushka.http.request import Request
from ushka.core.config import Config

async def get(request: Request, config: Config):
    query = request.query_params.get("q", "")
    api_key = config.get("SEARCH_API_KEY")

    # ... perform search using the query and API key ...

    return {"message": f"You searched for: {query}"}
```

In this example, you don't have to create the `request` or `config` objects yourself. Ushka's "assistant" sees that you need them and provides them automatically. This keeps your code clean, focused on the task at hand, and much easier to test.
