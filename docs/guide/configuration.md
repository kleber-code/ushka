# Configuration

Settings live in `ushka.toml`, next to the file that creates `Ushka()`. Keep only what differs from the defaults:

```toml
[app]
name = "Shop"

[database]
url = "postgresql://localhost/shop"
```

`ushka new` writes about ten lines like these. Every other key has a default, and
[All settings](settings.md) lists them.

## Four layers

Each layer overrides the one before it:

1. **Defaults** built into Ushka.
2. **`ushka.toml`**. Ushka only reads it, never rewrites it.
3. **`.env`** beside it, for secrets you keep out of Git.
4. **Environment variables**, named `USHKA_<SECTION>_<KEY>`: `USHKA_APP_DEBUG=true`.

`DATABASE_URL` also works for `[database] url`. Booleans accept `true/false`, `1/0`,
`yes/no`; lists are `a,b`. A bad value stops the app with a clear error.

## See what is in use

```bash
ushka config            # the common settings, and where each value came from
ushka config --all      # plus the advanced ones
ushka config --template # a complete, annotated ushka.toml
ushka check             # typos (`tain`) and wrong types (`csrf = "false"`)
```

## `.env` and secrets

`.env` takes `KEY=value` lines and `# comments`. The environment wins over it.
Secrets never go in `ushka.toml`:

```bash
# .env (git-ignored; `ushka new` creates it)
USHKA_APP_SECRET_KEY=paste-a-long-random-value-here
```

Sessions and [flash messages](flashing.md) need that key. With `debug` on and no
key, Ushka makes a temporary one per process. With `debug` off, `request.session`
raises until you set it. `ushka check --production` requires 32 characters or more:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## In code

```python
async def get(config):  # a parameter named `config`
    return {"name": config.APP_NAME, "debug": config.get("app_debug"), "from": config.source_of("app_debug")}
```

Add sections of your own (`[payments]`), read the same way. An unknown key inside a
built-in section is reported as a mistake.
