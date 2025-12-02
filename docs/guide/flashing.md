# Flashing Messages

Have you ever submitted a form and been redirected to a new page, only to see a little message at the top that says "Your profile has been updated successfully"? That's a "flashed" message.

Flashing is a way to send a one-time message from one request to the *next* one. It's like leaving a sticky note for the user that they'll see on the very next page they visit. Once they see it, the note disappears.

This is incredibly useful for providing feedback after an action.

## Sending a Message: `flash()`

To send a message, you use the `flash()` function. It requires the `request` object, the message you want to send, and an optional category.

Let's imagine a user is updating their profile.

```python
from ushka.utils.flash import flash, Category
from ushka.http.request import Request
from ushka.http.redirect import redirect

async def post(request: Request):
    # ... process the form data and update the user's profile ...

    flash(request, "Your profile has been updated!", Category.SUCCESS)

    return redirect("/profile")
```

Here's what happens:
1.  The user submits the form to this `post` handler.
2.  The code updates the profile in the database.
3.  We call `flash()`. This stores the message `"Your profile has been updated!"` and the category `"success"` in the user's session.
4.  The user is redirected to the `/profile` page.

## Displaying the Message in a Template

Now, on the `/profile` page, we need to display the message we just flashed.

Ushka provides a `flash_processor` that automatically makes flashed messages available in your templates. You can access them through the `messages` variable.

The `messages` variable is a list of tuples, where each tuple is `(category, message)`.

Here's how you might display them in your template:

```html
<!-- In your base layout or profile template -->

{% if messages %}
  <div class="flashes">
    {% for category, message in messages %}
      <div class="alert alert-{{ category }}">
        {{ message }}
      </div>
    {% endfor %}
  </div>
{% endif %}
```

When the `/profile` page is rendered, this code will:
1.  Check if there are any messages in the `messages` list.
2.  Loop through them.
3.  Render a `div` for each message, using the `category` to apply a CSS class (e.g., `alert-success`).
4.  Display the message text.

The magic is that once this page has been rendered, the messages are removed from the session. If the user refreshes the page, the messages will be gone.

## Message Categories

Categories help you style your messages. Think of them as labels. Ushka provides a few common categories out of the box in the `Category` enum:

*   `Category.SUCCESS`: For positive feedback, like "Item created successfully."
*   `Category.DANGER`: For errors or destructive actions, like "Could not delete item."
*   `Category.WARNING`: For important, but not critical, information.
*   `Category.INFO`: For general information (the default).

You can use these categories to apply different colors or icons to your messages, making your UI more intuitive for the user.

> **Ushka Tip:** Don't go crazy with flashing. It's for simple, direct feedback. If you need to convey complex information or preserve data across multiple pages, a different approach (like storing it in the database or using more complex session management) is probably a better fit. Keep it simple, keep it flashy!
