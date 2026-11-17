# Flashing Messages

A flash message is a one-time note from one request to the next: "Profile
saved", shown once on the page you are redirected to, then gone.

## Before you start: sessions

Flash messages are stored in the session, a signed cookie, so they need a
[secret key](configuration.md#env-and-secrets):

* Projects created with `ushka new` already have one in `.env`.
* `ushka dev` (debug on) generates a temporary key if none is set.
* Without a key and with debug off, `flash()` raises a `RuntimeError` that
  explains how to create one.

With debug off the session cookie is marked `Secure`, so browsers only send it
back over **HTTPS**. Serve production behind HTTPS (directly or through a
proxy), or messages will seem to vanish.

## Sending a message: `flash()`

```python
# routes/profile.py
from ushka.http import redirect
from ushka.templating import render
from ushka.templating.flash import Category, flash


async def get(request):
    return await render(request, "profile.html")


async def post(request):
    form = await request.form()
    # ... validate and save form["name"] ...
    flash(request, "Your profile has been updated!", Category.SUCCESS)
    return redirect("/profile")
```

`flash(request, message, category="info")` appends the message to the
session. The session cookie is saved on the redirect response automatically,
also when you `raise HTTPRedirect("/profile")` instead of returning it.

## Showing messages in a template

Every template rendered with `render()` gets a `messages` variable: a list of
`(category, message)` pairs. Rendering it also removes them from the session,
so they appear exactly once.

```html
<!-- templates/profile.html (or your base layout) -->
{% if messages %}
  <div class="flashes">
    {% for category, message in messages %}
      <div class="alert alert-{{ category }}">{{ message }}</div>
    {% endfor %}
  </div>
{% endif %}
```

Messages are autoescaped like any other value, so it is fine to include user
input in them.

## Reading messages in Python

Outside templates (in a JSON API, for example) use `get_flashed_messages()`.
It also removes the messages from the session.

```python
from ushka.templating.flash import get_flashed_messages


async def get(request):
    return {
        "messages": get_flashed_messages(request),                       # ["Saved!"]
        # or: get_flashed_messages(request, with_categories=True)        # [["success", "Saved!"]]
    }
```

Call it once per request: the first call takes the messages. Requests from
clients without a session cookie simply get an empty list.

## Categories

`Category` gives you four standard labels; any string works too.

| Value | Typical use |
| --- | --- |
| `Category.SUCCESS` (`"success"`) | Something worked. |
| `Category.DANGER` (`"danger"`) | An error or a destructive action. |
| `Category.WARNING` (`"warning"`) | Worth attention, not critical. |
| `Category.INFO` (`"info"`) | General information (the default). |

```python
flash(request, "Could not delete the item.", Category.DANGER)
flash(request, "Exported 42 rows.", "export")   # custom category
```

Categories are lower-cased, which makes them handy as CSS class names
(`alert-success`, `alert-danger`, ...).

> **Ushka Tip:** Keep flash messages short. The session lives in a cookie, and
> browsers limit cookies to about 4 KB.
