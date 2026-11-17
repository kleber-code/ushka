# Project structure

`ushka new hello` makes this layout. Every file has one job, and none is
required except the app itself.

```text
hello/
├── app.py              # app = Ushka()
├── ushka.toml          # settings, no secrets
├── .env                # USHKA_APP_SECRET_KEY, git-ignored
├── .env.example        # the same keys, empty, safe to commit
├── .gitignore
├── AGENTS.md           # rules for AI coding agents
├── routes/
│   └── index.py        # GET /
├── templates/
│   └── index.html
└── static/
    └── style.css
```

## The pieces

| Path | What it is | Learn more |
| --- | --- | --- |
| `app.py` | Creates the `Ushka()` object. `ushka dev` and `ushka run` serve `app:app`. | [Routing](routing.md) |
| `routes/` | One file per URL. Functions named `get`, `post`, `websocket`... answer it. | [Routing](routing.md) |
| `templates/` | Jinja2 templates, autoescaped. Yours win over built-in ones with the same name. | [Templates](templates.md) |
| `static/` | Files served at `/static/`. | [Static files](static_files.md) |
| `ushka.toml` | Settings. Only read, never rewritten. | [Configuration](configuration.md) |
| `.env` | Secrets and local overrides. Never commit it. | [Configuration](configuration.md#environment-variables-and-env) |
| `AGENTS.md` | Teaches coding agents your layout and the guard's rules. | [Ushka Guard](guard.md) |

Ushka looks for `routes/`, `templates/`, `static/` and `ushka.toml` in the
folder of the file that creates `Ushka()`, whatever directory you start the
server from.

## As the project grows

Nothing forces a layout, but this one works well:

```text
hello/
├── app.py
├── models.py           # ORM models (import them in app.py for migrations)
├── services/           # code your routes call
├── routes/
│   ├── index.py
│   ├── users/
│   │   ├── index.py            # /users
│   │   └── [user_id].py        # /users/<user_id>
│   └── api/
│       └── items.py            # /api/items
├── templates/
├── static/
├── migrations/         # created by `ushka db init`
└── tests/
```

- Keep routes thin: parse, call a function, return. Logic in plain modules is
  easy to test.
- Put the folders you expose over the web in `routes/`, and nothing else. A
  file in `routes/` is public the moment it defines `get` or `post`.
- Any route can also be a decorator in `app.py` (`@app.get("/health")`). Both
  styles mix freely. Set `[app] auto_discover = false` if you use decorators only.
- Handlers in your own packages are not covered by the compile-time guard
  rewrite unless you opt in; see [What it does not cover](guard.md#what-it-does-not-cover).

## Commands you will use

```bash
ushka dev            # develop, with reload
ushka routes list    # what is registered
ushka check          # settings and security
ushka verify app:app # attack your own routes
ushka run            # production
```

See the [CLI reference](cli.md).
