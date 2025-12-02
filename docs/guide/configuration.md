# Configuration

Every application has settings that can change depending on the environment. For example, your database URL will be different in development and production. Ushka provides a simple and flexible way to manage your application's configuration.

## The `config.toml` File

Ushka uses a `config.toml` file in the root of your project to store configuration settings. The TOML format is designed to be easy to read and write.

Here's an example of what a `config.toml` file might look like:

```toml
# config.toml

APP_NAME = "My Awesome Ushka App"
DEBUG = true

[database]
URL = "sqlite+aiosqlite:///my_app.db"

[api_keys]
STRIPE_SECRET_KEY = "your_stripe_secret_key_here"
```

## Accessing Configuration in Your Application

You can access your configuration settings using the `Config` object, which can be injected into your route handlers.

```python
from ushka.core.config import Config

async def get(config: Config):
    app_name = config.get("APP_NAME")
    debug_mode = config.get("DEBUG")

    # Accessing nested settings
    db_url = config.get("database.URL")

    return {"app_name": app_name, "debug": debug_mode, "db_url": db_url}
```

The `get()` method takes the key of the setting you want to retrieve. You can use dot notation (`.`) to access nested values.

### Providing Default Values

It's a good practice to provide a default value when you access a configuration setting. This prevents your application from crashing if the setting is not defined in the `config.toml` file.

You can provide a default value as the second argument to the `get()` method:

```python
# If "PORT" is not set in the config file, it will default to 8000.
port = config.get("PORT", 8000)
```

## Environment Variables

For sensitive information like API keys and database credentials, it's best to use environment variables instead of storing them directly in your `config.toml` file.

Ushka will automatically look for an environment variable with the same name as the setting you're trying to access. If it finds one, it will use the value from the environment variable, overriding the value in the `config.toml` file.

For example, if you have this in your `config.toml`:

```toml
[database]
URL = "sqlite:///default.db"
```

And you set an environment variable like this:

```bash
export DATABASE_URL="postgresql://user:pass@host/prod_db"
```

Then `config.get("database.URL")` will return the value from the environment variable.

> **Ushka Tip:** Using environment variables for sensitive data is a security best practice. It prevents you from accidentally committing your secrets to a version control system like Git. You can use a `.env` file to manage your environment variables in development.
