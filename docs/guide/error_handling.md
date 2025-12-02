# Error Handling

Even in the best-written applications, things can go wrong. A user might try to access a page that doesn't exist, a database connection might fail, or an unexpected bug might occur. How your application handles these errors is crucial for a good user experience.

Ushka provides a simple yet powerful way to handle errors.

## The Default Error Pages

By default, Ushka comes with sensible error pages for common HTTP errors:

*   **404 Not Found:** When a user requests a URL that doesn't match any of your routes.
*   **500 Internal Server Error:** When an unhandled exception occurs in your application code.

In a development environment, the 500 error page will be a detailed "debug" page, showing the full traceback of the exception. This is incredibly helpful for finding and fixing bugs.

> **Ushka Tip:** In a production environment, the detailed debug page is disabled for security reasons. Users will see a generic "Internal Server Error" message. You should never run your application in debug mode in production!

## Custom Error Pages

While the default error pages are useful, you'll likely want to create your own custom error pages that match the look and feel of your site.

To do this, you can create templates in your `templates` directory with the name of the error code, like `404.html` or `500.html`.

For example, to create a custom 404 page, you could create a file at `templates/404.html`:

```html
<!-- templates/404.html -->
{% extends "layout.html" %}

{% block content %}
  <h1>Oops! Page Not Found</h1>
  <p>We couldn't find the page you were looking for.</p>
  <a href="/">Go back home</a>
{% endblock %}
```

Ushka will automatically detect this file and use it to render 404 errors.

## Raising Errors

Sometimes, you need to intentionally stop the request and show an error page. For example, if a user is trying to access a resource they don't have permission to see.

Ushka provides a set of HTTP exception classes in `ushka.http.exceptions` that you can use for this.

```python
from ushka.http.exceptions import NotFound, Forbidden
from ushka.features.orm import db

class Post(db.Model):
    # ... model definition ...

async def get(id: int):
    post = await Post.get(id)
    if not post:
        raise NotFound("Sorry, we couldn't find that post.")

    # A simple permission check
    if not current_user.can_view(post):
        raise Forbidden("You don't have permission to view this post.")

    return await render(request, "post_detail.html", {"post": post})

```

When you raise one of these exceptions, Ushka will catch it and render the appropriate error page. For example, `raise NotFound()` will result in a 404 page.
