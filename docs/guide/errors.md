# 🐛 Error Handling: Because Even Perfect Apps Stumble! 🤷‍♀️

Robust error handling is crucial for any web application. Ushka provides a visually pleasing and informative way to handle errors during development, and a more graceful, user-friendly approach in production. Minimal fuss, maximum clarity.

## 🤯 Debug Mode Errors ("Ushka Panic!")

When your app is running with `debug = true` in your `ushka.toml` file, any unhandled exception will trigger the glorious **"Ushka Panic!"** page. Yes, we named it that.

![Ushka Panic Screenshot](/assets/ushka_panic.png)

This page is actually designed to make debugging less of a headache:

*   **Full Stack Trace:** See the entire tragic sequence of calls that led to the error. Good times.
*   **Code Context:** For each frame in the stack, you get to see the actual lines of code where things went wrong, with the exact line highlighted. No excuses now.
*   **Local Variables:** Inspect the local variables in each frame. Find out what your variables were *really* up to when the error hit.
*   **Copy Traceback:** A single button to copy the entire raw traceback. Perfect for pasting into StackOverflow, ChatGPT, or your colleague's Slack.

## 🤫 Production Errors: Keep it Discreet!

When `debug = false`, Ushka plays it cool. For security reasons (and to not scare your users), we won't show the detailed panic page. Instead, a generic, stylized error template takes its place.

Ushka comes with default templates for common HTTP errors, but you're more than welcome to customize them.

### 🎨 Overriding Error Templates: Your Style, Your Rules!

To provide your own custom error pages, simply create a `templates` directory in your project root and add files with these names:

*   `templates/error.html`: Your go-to for generic errors (e.g., a missing 404 page).
*   `templates/debug_error.html`: You *can* customize the debug page too, if you're feeling particularly artistic, though Ushka's default is pretty decent.

When an error occurs, Ushka will check for your custom `templates/error.html` first. If it's not there, it falls back to its trusty default.

### 🚩 Raising HTTP Errors: Sometimes You Just Gotta!

Sometimes, you need to manually tell the app, "Hey, something's not right here!" For example, if a user requests an item that, tragically, doesn't exist.

You can do this by raising an `HTTPError` or `HTTP_NotFound` exception. It's like gently but firmly pointing out a problem.

```python
from ushka.http.exceptions import HTTPError, HTTP_NotFound

@app.get("/items/{item_id}")
def get_item(item_id: int):
    item = find_item_in_db(item_id)
    if not item:
        # User asked for something that isn't there. Tough luck.
        raise HTTP_NotFound(message=f"Item with ID {item_id} decided to go on vacation.")

    if not user_has_permission_to_view(item):
        # Access denied. You shall not pass!
        raise HTTPError(status_code=403, message="You lack the proper clearance for this item.")
```
