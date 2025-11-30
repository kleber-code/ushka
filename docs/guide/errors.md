# Error Handling

Robust error handling is crucial for any web application. Ushka provides a visually pleasing and informative way to handle errors during development, and a flexible way to show custom error pages in production.

## Debug Mode Errors ("Ushka Panic")

When you're running your app with `debug = true` in your `ushka.toml` file, any unhandled exception will trigger the **"Ushka Panic"** page.

![Ushka Panic Screenshot](https://raw.githubusercontent.com/kleber-code/ushka/main/src/ushka/internal/assets/ushka_panic.png)

This page is designed to make debugging easier:

- **Full Stack Trace:** See the exact sequence of calls that led to the error.
- **Code Context:** For each frame in the stack, you can see the lines of code where the error occurred, with the exact line highlighted.
- **Local Variables:** Inspect the local variables in each frame to understand the state of your application at the time of the error.
- **Copy Traceback:** A one-click button to copy the entire raw traceback, ready to be pasted into a search engine or a chat with a colleague.

## Production Errors

When `debug = false`, Ushka will not show the detailed panic page to your users for security reasons. Instead, it will render a generic error template.

Ushka comes with default templates for common HTTP errors, but you can easily override them.

### Overriding Error Templates

To provide your own custom error pages, create a `templates` directory in your project root and add files with the following names:

- `templates/error.html`: For generic errors (e.g., 404 Not Found).
- `templates/debug_error.html`: You can also customize the debug page if you wish, though it's less common.

When an error occurs, Ushka will look for your custom `templates/error.html` first before falling back to its own default template.

### Raising HTTP Errors

Sometimes you need to manually trigger an HTTP error. For example, if a user requests an item that doesn't exist in your database.

You can do this by raising an `HTTPError` or `HTTP_NotFound` exception.

```python
from ushka.http.exceptions import HTTPError, HTTP_NotFound

@app.get("/items/{item_id}")
def get_item(item_id: int):
    item = find_item_in_db(item_id)
    if not item:
        # This will trigger a 404 Not Found response
        raise HTTP_NotFound(message=f"Item with ID {item_id} not found.")

    if not user_has_permission_to_view(item):
        # This will trigger a 403 Forbidden response
        raise HTTPError(status_code=403, message="You do not have permission to view this item.")
```
