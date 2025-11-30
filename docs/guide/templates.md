# Templates

Ushka has first-class support for rendering HTML templates using **Jinja2**.

## Setting up Templates

By default, Ushka will look for a `templates` directory in your project root.

### The `render` function

To render a template, you'll need to import the `render` function from `ushka.features.template`.

```python
from ushka.features.template import render

@app.get("/")
def home():
    # Renders the 'index.html' template
    # Passes a context dictionary with 'username'
    return render("index.html", {"username": "Guest"})
```

### Creating a Template

Create a `templates` folder in your project root. Inside, create a file named `index.html`.

```html
<!-- templates/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ushka App</title>
</head>
<body>
    <h1>Hello, {{ username }}!</h1>
    <p>Welcome to an app powered by Ushka.</p>
</body>
</html>
```

The `render` function takes the template name and an optional context dictionary, which makes variables available inside the template.