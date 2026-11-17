# Contributing

Thank you for helping with Ushka. Bug reports, fixes, documentation and feature ideas are all welcome.
Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

Ushka is in beta and maintained by one person, so reviews can take a few days.

## Reporting a bug

Open an [issue](https://github.com/kleber-code/ushka/issues) with:

- a short, specific title;
- the steps to reproduce it, ideally a small app;
- the Ushka and Python versions (`ushka --version`);
- the error output and, if relevant, your `ushka.toml` without secrets.

A security problem is not a public issue: see the [security policy](SECURITY.md).

## Suggesting a feature

Open an issue that says what problem it solves and how it would be used. Ushka aims to stay easy,
fast, hackable and modular, so a feature should turn on in one line and be replaceable. Features
usually fit as a piece (`app.use(...)`).

## Documentation

Fix what is unclear or wrong with a pull request. The sources are in `docs/`, and
`ushka docs check docs --api ushka` verifies links and anchors.

## Code

```bash
git clone https://github.com/<you>/ushka.git
cd ushka
uv venv .venv
uv pip install -e ".[orm,docs,crypto]" pytest pytest-asyncio pyyaml starlette fastapi django httpx
.venv/bin/pytest                         # run it on 3.10 and 3.14 too
.venv/bin/ushka docs check docs --api ushka
```

PDM and the lock file (`pdm.lock`) are what CI uses; `pdm install -d -G orm -G docs -G crypto` does the same.

Read [`AGENTS.md`](../AGENTS.md) before changing code: it explains the layout, the design rules and the
conventions every change follows.

## Pull requests

- Open it against `main`, with one change per pull request.
- Say what it does, why, and how to test it.
- Add tests, and a line in `CHANGELOG.md` for any change in behaviour.
- Update the docs when behaviour changes. Every new setting goes in `SCHEMA`
  (`src/ushka/core/settings.py`), and the generated docs must be regenerated.
- Run `ruff check` on the files you touched.
