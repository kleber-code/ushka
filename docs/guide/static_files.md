# Serving Static Files

Web applications aren't just about dynamic content. You also need to serve static files like CSS, JavaScript, images, and fonts. Ushka makes this easy.

## The `static` Directory

By default, Ushka will serve any files placed in a directory named `static` in your project's root.

For example, if you have a file at `static/css/style.css`, you can access it in your browser at the URL `/static/css/style.css`.

## How to Link to Static Files in Templates

To link to your static files in your Jinja2 templates, you can use the `url_for` function. However, for simplicity and since the static path is fixed, you can also just write the path directly.

```html
<!DOCTYPE html>
<html>
<head>
    <title>My Ushka App</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <h1>Welcome!</h1>
    <img src="/static/images/logo.png" alt="My App Logo">
</body>
</html>
```

## Changing the Static Directory

If you want to use a different directory for your static files, you can configure it in your application's settings. (See the [Configuration](./configuration.md) guide for more details).

For example, to use a directory named `public` instead of `static`, you would set `STATIC_DIR` in your config file.

> **Ushka Tip:** It's a good practice to organize your static files into subdirectories, such as `css`, `js`, `images`, etc. This keeps your project tidy and makes it easier to manage your assets as your application grows.
