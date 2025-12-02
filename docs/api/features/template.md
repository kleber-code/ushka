## `module`

```python
This module provides templating functionality using Jinja2.

It configures a Jinja2 environment that searches for templates first in the
project's 'templates' directory and then falls back to the framework's
internal default templates. Auto-escaping is enabled for HTML and XML files
to prevent XSS vulnerabilities.
```

## `render`

```python
Renders a Jinja2 template with the given context.

Args:
    template_name: The name of the template file to render.
    context: A dictionary of variables to pass to the template.

Returns:
    The rendered template as an HTML string.
```

