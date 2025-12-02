# My Personal Control Panel: `ushka.toml`

Oh, this little file? This is my `ushka.toml`. It's where I keep all my little secrets and preferences. Think of it as my diary, but instead of teenage angst, it's filled with crucial configuration details. And yes, I'm so thoughtful, I'll even create one for you if you're too lazy. You're welcome.

## What's Hiding in My Diary?

This file holds all the essential settings for *my* application (which, by extension, is *your* application now). It's where you get to decide where I sleep (my host and port) and whether I'm feeling playful (debug mode) or all business (production mode).

Here's a peek inside:

```toml
# ushka.toml (I'll make this for you, so don't worry your pretty little head)

[ushka]
version = "0.3.0" # My current version, always up-to-date.
workdir = "/path/to/your/project" # Where I'm currently residing.

[server]
host = "127.0.0.1" # Where I'll be listening. Default is home sweet home.
port = 8000 # My favorite number, apparently.
workers = 1 # How many of me do you want running? Be gentle.
ushka_suppress_uvicorn = true # Do you want Uvicorn to be quiet?

[app]
name = "Ushka App" # What do you call me?
debug = true # Do you want to see my tantrums or my best behavior?
auto_discover = true # Should I sniff out your routes automatically?
secret_key = "sussy_secret_key" # My super-secret key for important stuff. Don't tell anyone.

[static]
enable = false # Should I serve static files?
url = "/static" # Where should I serve them from?
dir = "static" # Where do you keep your static files?
```

## Decoding My Secrets (The Sections):

### `[ushka]` - About Me

This section provides details about my core.

*   **`version`** (string):
    My current version. Always evolving, always improving.
*   **`workdir`** (string):
    The absolute path to your project's working directory. I like to know my surroundings.

### `[server]` - My Cozy Nook

This section dictates my basic networking manners.

*   **`host`** (string, default: `"127.0.0.1"`):
    The IP address I'll be eavesdropping on. If you want me to shout across your network, change this to `"0.0.0.0"`. But don't blame me if things get noisy.
*   **`port`** (integer, default: `8000`):
    The secret knock to get my attention. Choose wisely; some numbers are already taken.
*   **`workers`** (integer, default: `1`):
    How many instances of me should be running? More of me means more power, but also more responsibility.
*   **`ushka_suppress_uvicorn`** (boolean, default: `true`):
    Do you want Uvicorn, my trusty companion, to keep quiet about its logs? I'm fine with the attention, but sometimes silence is golden.

### `[app]` - My Personality Traits

This section defines who I am on a deeper level. (UwU)

*   **`name`** (string, default: `"Ushka App"`):
    What do you call me? My official name, if you will.
*   **`debug`** (boolean, default: `true`):
    This is paramount! It's like asking if I'm wearing my "all-seeing eye" glasses.
    *   If `true`, I'm in **Debug Mode**. This means:
        *   You'll see my full, unadulterated "Ushka Panic!" whenever something goes wrong. It's quite a show.
        *   I might even reload when you change code. Convenient, isn't it?
        *   I'll be extra chatty in the logs. You get to hear all my thoughts.
    *   If `false`, I'm in **Production Mode**. This means:
        *   I'll put on my polite face and show generic error pages. Security, darling.
        *   I'll prioritize performance. No time for jokes.
        *   I'll be much quieter. Sometimes, silence is golden.
*   **`auto_discover`** (boolean, default: `true`):
    Should I automatically discover your routes based on your file structure? I'm pretty good at sniffing them out.
*   **`secret_key`** (string, default: `"sussy_secret_key"`):
    My super-secret key for important stuff. Don't tell anyone. If you don't set this, I'll generate a secure one for you. I'm so thoughtful.

### `[static]` - My Treasure Trove

This section handles all your static assets.

*   **`enable`** (boolean, default: `false`):
    Should I serve static files for you? If you want me to, you need to enable me here.
*   **`url`** (string, default: `"/static"`):
    The URL prefix where your static files will be served. For example, `/static/my-cat.png`.
*   **`dir`** (string, default: `"static"`):
    The directory where I expect to find your trinkets: your CSS, your JS, your cat pictures. By default, I'll peek into a `static` directory right in your project's root. Easy peasy.

## How I Use This Information (and how you can too)

When you tell me to `app.run()`, I casually glance at my `ushka.toml` file. If you dare to give me direct orders (arguments to `app.run()`), I'll prioritize those. It's my little way of showing flexibility.

But here's a secret for you: you can also access my configuration directly in your routes! Just ask for the `Config` object, and I'll graciously provide it.

```python
from ushka.core.config import Config

def get(config: Config):
    my_version = config.get("USHKA_VERSION") # Access with uppercase section_attribute
    debug_mode = config.get("APP_DEBUG")
    static_files_enabled = config.get("STATIC_ENABLE")
    return {"version": my_version, "debug": debug_mode, "static_enabled": static_files_enabled}
```

Remember, my `ushka.toml` keeps everything organized. So no more digging through ancient scrolls to find a simple setting. (¬‿¬)