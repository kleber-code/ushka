# ⚙️ Ushka.toml: Your App's Little Control Panel! 🎮

Ushka is a big fan of minimalism, especially when it comes to configuration. That's why we use `ushka.toml` – a neat, tidy file that lets you tweak your app's behavior without wrestling with complex code. And the best part? Ushka creates one for you automatically if it doesn't exist! Talk about zero-config!

## What's Inside `ushka.toml`?

This file holds all the essential settings for your Ushka application. It's where you define things like where your app lives (host and port) and whether it's in a playful debug mode or serious production mode.

Here's what a typical `ushka.toml` might look like:

```toml
# ushka.toml (Auto-generated on first run if not present)

[server]
host = "127.0.0.1"
port = 8000

[app]
debug = true
static_dir = "static"
```

## Understanding the Sections:

### `[server]` - Where Your App Hangs Out

This section controls the basic networking aspects of your Ushka application.

*   **`host`** (string, default: `"127.0.0.1"`):
    The IP address your server will listen on. Use `"0.0.0.0"` if you want your app to be accessible from other devices on your network.
*   **`port`** (integer, default: `8000`):
    The port number your server will use. Pick any available port you like!

### `[app]` - Your App's Personality!

This section defines general application-wide settings.

*   **`debug`** (boolean, default: `true`):
    This is super important!
    *   If `true`, Ushka is in **Debug Mode**. This means:
        *   Detailed error pages (our famous "Ushka Panic!") will be displayed in your browser.
        *   Code changes might trigger a server reload (depending on how you run Ushka).
        *   More verbose logging might be enabled.
    *   If `false`, Ushka is in **Production Mode**. This means:
        *   Generic error pages are shown to users for security reasons.
        *   Performance optimizations are prioritized.
        *   Less verbose logging.
*   **`static_dir`** (string, default: `"static"`):
    The directory where your static files (CSS, JS, images) are located. By default, Ushka will look for a `static` directory in your project's root.


## How Ushka Uses It

When you run `app.run()`, Ushka automatically reads these settings from `ushka.toml`. If you provide arguments directly to `app.run()`, those will take precedence. It's a neat way to override settings for specific runs without changing the file!

Remember, `ushka.toml` keeps things tidy and centralized. No more hunting through code for basic configurations! 💖
