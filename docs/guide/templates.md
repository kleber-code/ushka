# 🖼️ Templates: Making Your Pages Pop! ✨

Ushka, being the sensible framework it is, provides first-class support for rendering HTML templates using **Jinja2**. It's pretty straightforward to get your web pages looking sharp without too much fuss.

## 🏡 Setting Up Your Template Directory

By default, Ushka is quite intuitive. It'll automatically look for your templates in a folder named `templates` right in your project's main directory. Logical, right?

### The `render` Function: Your HTML Delivery Service! 🪄

To actually use a template, you'll need the `render` function from `ushka.features.template`. Because, you know, templates don't render themselves.

```python
from ushka.features.template import render

@app.get("/")
def home():
    # Renders the 'index.html' template
    # Passes a context dictionary with 'username'. Because templates love data.
    return render("index.html", {"username": "Guest"})
```

### 🎨 Crafting Your First Template: It's Not Rocket Science!

Just create a `templates` folder in your project root. Inside, pop in a file named `index.html`.

```html
<!-- templates/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ushka App</title>
</head>
<body>
    <h1>Hello there, {{ username }}!</h1>
    <p>Welcome to an app powered by Ushka. We try not to be boring.</p>
</body>
</html>
```

The `render` function takes the template name (duh) and an optional dictionary of context. These variables become available inside your template. It's almost like magic, but mostly just good engineering. 💖