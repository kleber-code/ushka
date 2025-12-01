# 💉 Dependency Injection: Ushka's Clever Helpers! 🧠

Ever wished your functions just *knew* what they needed without you having to manually fetch everything? Well, Ushka's got your back! Our Dependency Injection (DI) system is like having a super smart assistant that magically hands your functions exactly what they ask for. It's minimalist, it's efficient, and frankly, it's a bit brilliant.

## What's the Big Deal About DI?

Imagine you have a function that needs a `Request` object (to peek at incoming data) and maybe some parameters from the URL. Without DI, you'd be passing these around manually or digging them out of global contexts. Boring!

With DI, your function simply declares its needs using Python's type hints. Ushka then looks at what your function *wants* and, if she has it, provides it. It decouples your code, makes it easier to test, and keeps things wonderfully tidy.

## How Ushka Does Its Magic! ✨

Ushka's DI is delightfully simple. You just type-hint the parameters your route function needs, and Ushka's little helpers spring into action.

### 📦 Injecting the `Request` Object

The most common "dependency" your route functions will need is the `Request` object itself.

```python
from ushka import Request

@app.get("/hello")
def say_hello(request: Request):
    # Ushka saw you needed the Request object and delivered!
    return f"Hello from {request.client.host}! You used method: {request.method}"
```
See? No `Request()` call, no manual passing. Just type-hint and receive.

### 🗺️ Injecting Path Parameters

Remember those dynamic paths like `/users/{user_id}`? Ushka's DI system also handles those with a charming grace.

```python
# In your routes/users/[user_id].py (File-Based Routing)
# or using a decorator: @app.get("/users/{user_id}")

def get(user_id: int): # Type-hint 'user_id' as an integer
    # Ushka automatically converts the path segment 'user_id' to an int for you!
    return {"message": f"Fetching user with ID: {user_id}. Hope they're nice!"}
```
Ushka not only injects the parameter but also performs **automatic type conversion**! If `user_id` in the URL isn't an integer, Ushka will raise a friendly (but firm) error, preventing headaches later.

## Why We Love It (and You Will Too!) 💖

*   **Clean Code:** Your function signatures are clear and concise. They state exactly what they need.
*   **Testability:** Want to test your route function? Just pass in a mock `Request` object and your desired parameters. Easy-peasy!
*   **Modularity:** Functions become independent units, making your codebase easier to manage and understand.
*   **Less Boilerplate:** No more manually parsing path segments or pulling data out of a generic request object. Ushka handles it.

Dependency Injection in Ushka is designed to be unobtrusive and highly effective, letting you focus on writing your awesome application logic. It's just another way Ushka tries to make your coding life a little brighter. ✨
