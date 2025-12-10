# Templates

Most web applications don't just return text or JSON; they return rich HTML pages. A templating engine helps you do this by combining static HTML with dynamic data.

Ushka uses the popular and powerful **Jinja2** templating engine. If you've ever worked with Django or Flask, you'll feel right at home.

## Rendering a Template

Imagine you have a template file named `hello.html` in a `templates` directory in your project's root.

```html
<!-- templates/hello.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Hello from Ushka!</title>
</head>
<body>
    <h1>Hello, {{ name }}!</h1>
</body>
</html>
```

This template has a placeholder `{{ name }}`. Our goal is to replace this with a real value from our Python code.

To do this, you use the `render` function in your route handler.

```python
# In routes/greet.py
from ushka.features.template import render
from ushka.http.request import Request

async def get(request: Request):
    # The second argument is the template name.
    # The third argument is the "context" dictionary.
    return await render(request, "hello.html", {"name": "World"})
```

When a user visits the `/greet` URL, Ushka will:
1.  Find the `hello.html` template.
2.  Take the context dictionary `{"name": "World"}`.
3.  Replace `{{ name }}` with `"World"`.
4.  Send the final HTML back to the user's browser.

The result is a page that says: "Hello, World!".

## Template Superpowers: Control Flow and More

Jinja2 is more than just a placeholder-replacer. It's a full-featured programming language for your templates.

You can use `if` statements:
```html
{% if user.is_authenticated %}
    <p>Welcome back, {{ user.name }}!</p>
{% else %}
    <p>Welcome, guest!</p>
{% endif %}
```

And `for` loops:
```html
<ul>
{% for product in products %}
    <li>{{ product.name }} - ${{ product.price }}</li>
{% endfor %}
</ul>
```

This allows you to build complex, dynamic pages with ease.

> **Ushka Tip:** Think of your Python code as the "brains" and your templates as the "face" of your application. The brains should do the heavy lifting (like fetching data from the database), and the face should focus on making it look good. Keep your templates clean and free of complex logic.

## Context Processors: The Gift That Keeps on Giving

Imagine you need the current user's name to be available in *every* template. You could pass it in the context dictionary of every single `render` call, but that's repetitive.

A context processor is a function that automatically adds data to the template context for every request. It's a "gift" of data that you give to all your templates.

Ushka has a built-in context processor for [flashing messages](./flashing.md), but you can also create your own.

Let's say you have an `auth` system that puts the current user on the `request` object. You could write a context processor like this:

```python
# In a file like `my_app/context_processors.py`
from ushka.http.request import Request

async def user_processor(request: Request) -> dict:
    return {"current_user": request.user}
```

You would then add this processor when you initialize your application. Once registered, the `current_user` variable will be available in all your templates, automatically!

```html
<nav>
    <a href="/">Home</a>
    {% if current_user.is_authenticated %}
        <a href="/profile">{{ current_user.name }}</a>
    {% else %}
        <a href="/login">Login</a>
    {% endif %}
</nav>
```

By using templates and context processors effectively, you can create a clean separation between your application's logic and its presentation, leading to more maintainable and scalable code.
