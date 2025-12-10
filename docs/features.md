# Features

Ushka comes with a variety of features designed to make web development in Python a breeze. Here's a look at some of the highlights:

## Filesystem-Based Routing

Forget complex route configuration files. With Ushka, your URL structure mirrors your filesystem. Create a file, define a function, and your route is live.

*   `routes/index.py` → `/`
*   `routes/users/profile.py` → `/users/profile`

This intuitive approach makes it easy to organize your project and find your code.

## Asynchronous from the Ground Up

Built on modern Python `asyncio`, Ushka is fast and scalable. Handle thousands of concurrent connections with ease, perfect for real-time applications, APIs, and high-traffic websites.

## Active Record ORM

Our built-in Object-Relational Mapper (ORM) is based on the powerful SQLAlchemy library, but with a simplified, Active Record-style interface.

```python
# Example of creating a new user
user = await User.create(name="Alice", email="alice@example.com")
```

The ORM is fully asynchronous, so you can interact with your database without blocking the event loop.

## Jinja2 Templating

Ushka uses the popular and powerful Jinja2 templating engine. We've extended it with asynchronous support and helpful features like context processors.

```python
# In your route handler
return await render(request, "profile.html", {"user": user})
```

## Flashing Messages

Easily pass messages between requests. The "flash" system is perfect for showing notifications to users after they perform an action.

```python
# In your route handler
flash(request, "Profile updated successfully!", "success")

# In your template
{% for category, message in messages %}
  <div class="alert alert-{{ category }}">{{ message }}</div>
{% endfor %}
```

## Simple Dependency Injection

Keep your code clean and testable. Ushka's simple dependency injection system can automatically provide `Request`, `Response`, and `Config` objects to your route handlers.

```python
# The `request` object is automatically injected
async def my_route(request: Request):
    user_agent = request.headers.get("User-Agent")
    return {"message": f"Your user agent is: {user_agent}"}
```

## And More...

*   **Static File Serving:** Serve your CSS, JavaScript, and images with ease.
*   **Easy Configuration:** Manage your application's settings with a simple and flexible configuration system.
*   **Helpful Error Pages:** Debugging is easier with clear and informative error pages.
*   **Command-Line Interface:** A handy CLI for running your development server and other tasks.
