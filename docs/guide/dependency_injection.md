# Dependency Injection

Dependency Injection (DI) might sound like a complex computer science topic, but in Ushka, it's a simple and powerful feature that helps you write cleaner, more organized, and more testable code.

## The "Assistant" Analogy

We used this analogy in the [Routing](./routing.md) guide, but it's worth repeating:

Imagine you're a busy chef in a kitchen (your route handler). You need ingredients like the current `request` details, a `response` object to fill, or your application's `config`. Instead of running around the kitchen to get these things yourself, you have an assistant who brings them to you right when you need them.

That's what dependency injection is in Ushka.

## How It Works

When a request comes in, Ushka looks at the signature of the route handler function that's about to be called. If it sees parameters with specific types that it recognizes, it will automatically "inject" an instance of that type into the function call.

The main "injectable" types that Ushka provides out of the box are:

*   `ushka.http.request.Request`: The incoming request object, containing headers, query parameters, body, etc.
*   `ushka.http.response.Response`: A new, empty response object that you can customize.
*   `ushka.core.config.Config`: The application's configuration object.

Here's an example that uses all three:

```python
from ushka.http.request import Request
from ushka.http.response import Response
from ushka.core.config import Config

async def my_handler(request: Request, response: Response, config: Config):
    # Get the user's name from the query parameters
    user_name = request.query_params.get("name", "Guest")

    # Get the app name from the configuration
    app_name = config.get("APP_NAME", "My App")

    # Set the content of the response
    response.text = f"Hello, {user_name}! Welcome to {app_name}."

    # Set a custom header
    response.headers["X-Greeting"] = "Hello"

    return response
```

Notice that we never had to create instances of `Request`, `Response`, or `Config`. Ushka's "assistant" saw that our function needed them and provided them for us.

## Why Is This Useful?

1.  **Cleaner Code:** Your route handlers can focus on their specific job, without being cluttered with the boilerplate code of creating and managing these common objects.

2.  **Decoupling:** Your handlers don't need to know *how* to get these objects. They just declare that they *need* them. This makes your code more modular.

3.  **Easier Testing:** When you write tests for your route handlers, you can easily create mock (fake) versions of these dependencies and pass them into your functions. This allows you to test your handlers in isolation, without needing a full application server.

> **Ushka Tip:** While Ushka's built-in dependency injection is simple, it's a powerful pattern. As your applications grow, you can even build your own dependency injection system for your own services and objects. It's a great way to manage complexity and build maintainable software.
