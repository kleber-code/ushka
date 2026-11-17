# Why Ushka changed

Ushka started as a small, friendly async framework with filesystem routing.
That is still true, but a small, friendly async framework is not a reason
to choose Ushka in 2026. FastAPI, Litestar, Django and Flask already cover
that well, with years of documentation behind them.

So from 0.5 Ushka has a clear purpose:

> **Ushka is the Python web framework where insecure code, whether you or an
> AI wrote it, does not run silently. It stops and tells you how to fix it.**

## The problem

More and more web code is written with AI assistants, and the studies agree
that a large share of it is insecure. Veracode's ongoing benchmark of more
than 100 models found that
[about 45% of generated samples contain OWASP Top 10 flaws](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-codegen-vulnerability-debt-20260406-csa/),
and that rate has not improved while general coding scores have. At the same
time, apps now feed **model output** back into HTML, redirects, URLs and SQL,
and that output can be steered by prompt injection.

The bugs are old ones (XSS, open redirects, path traversal, SQL injection),
and frameworks already offer the safe tools. The problem is that nothing
stops you from using the unsafe way.

## What Ushka does about it

- **Untrusted data is a type.** Request values and model output arrive as
  `Untrusted`, and the dangerous sinks refuse them. See [Ushka Guard](guide/guard.md).
- **The check runs on your real code.** It does not depend on a linter, a
  review or a paid agent.
- **Errors teach.** Every block names the risk and the exact fix, both as text
  and as JSON for coding agents.
- **Python 3.14 t-strings are first class.** `t"<h1>{name}</h1>"` and
  `db.execute(t"... {value}")` are safe by construction.

## What stays the same

Filesystem routing, decorators, the Active Record ORM, Jinja2, sessions, the
CLI and `ushka.toml` all keep working. Ushka will also keep a friendly
personality.

## What came next

The plan from 0.5 is now in the code:

- [Security middleware](guide/security.md) on by default (CSRF, security headers,
  CORS, trusted hosts).
- [Routes as tools for AI agents (MCP)](guide/agents.md), each with declared
  capabilities and approval for sensitive actions.
- [`ushka verify`](guide/verify.md), which sends attack payloads to your own routes.
- [`ushka.guard` for FastAPI, Starlette and Django](guide/guard-frameworks.md).
  Publishing it as a standalone package is still ahead.

See the [roadmap](roadmap.md) and the [changelog](https://github.com/kleber-code/ushka/blob/main/CHANGELOG.md).
