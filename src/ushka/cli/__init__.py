"""The ``ushka`` command-line interface (argparse, standard library only)."""

from __future__ import annotations

import argparse
import os
import sys


def _load_db_command():
    """Imports ``ushka.cli.commands.db`` lazily: it needs the ``orm`` extra."""
    try:
        from ushka.cli.commands import db
    except ImportError as exc:
        missing = getattr(exc, "name", None) or str(exc)
        raise SystemExit(
            f"The 'db' command requires the ORM extra (missing: {missing}). "
            "Install it with: pip install 'ushka[orm]'"
        ) from exc
    return db


def _version() -> str:
    from ushka.core.config import _package_version

    return _package_version()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ushka",
        description="Ushka: the web framework where untrusted data cannot slip through.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"ushka {_version()}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("new", help="create a new project")
    p.add_argument("project_name", help="directory/name of the project")

    for name, help_text in (
        ("dev", "development server (reload, debug on)"),
        ("run", "production server"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("app", nargs="?", default="app:app", help="module:attribute (default: app:app)")
        p.add_argument("--host", default="", help="bind address (default: [server] host)")
        p.add_argument("--port", type=int, default=0, help="port (default: [server] port)")

    p = sub.add_parser("check", help="validate configuration and security settings")
    p.add_argument(
        "--production", action="store_true", help="also require debug off and a secret key"
    )

    p = sub.add_parser("config", help="list every setting, its value and where it came from")
    p.add_argument("section", nargs="?", default="", help="only this section, e.g. security")
    p.add_argument("--describe", action="store_true", help="also explain each setting and its environment variable")
    p.add_argument("--all", action="store_true", help="also list the advanced (rarely changed) settings")
    p.add_argument("--template", action="store_true", help="print a complete, annotated ushka.toml")
    p.add_argument("--markdown", action="store_true", help="print the settings reference as Markdown (used by the docs)")

    p = sub.add_parser("verify", help="attack your own routes with hostile payloads and report what got through")
    p.add_argument("app", help="the app as module:attribute, e.g. app:app")
    p.add_argument("--include-writes", action="store_true", help="also probe POST/PUT/PATCH/DELETE routes (runs their handlers: use a test database)")
    p.add_argument("--param", action="append", default=[], metavar="NAME", help="also probe this query parameter (repeatable)")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--fail-on", choices=["high", "medium", "none"], default="medium", help="lowest severity that makes the exit status 1 (default: medium)")
    p.add_argument("--skip-exempt", action="store_true", help="leave out the routes exempt from CSRF ([security] csrf_exempt_paths); they are probed by default")
    p.add_argument("--as-session", action="append", default=[], metavar="KEY=VALUE", help="probe as a logged-in user: forge a session with this item (repeatable; 1 and true become int and bool). Test tool")
    p.add_argument("--cookie", action="append", default=[], metavar="NAME=VALUE", help="send this cookie with every probe, e.g. a real session cookie (repeatable)")
    p.add_argument("--header", action="append", default=[], metavar="'NAME: VALUE'", help="send this header with every probe, e.g. 'Authorization: Bearer ...' (repeatable)")

    p = sub.add_parser("session", help="print a forged session cookie (name=value) to test as a logged-in user")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", dest="items", help="a session item, e.g. uid=1 (repeatable)")
    p.add_argument("--app", default="app:app", help="module:attribute (default: app:app)")
    p.add_argument("--allow-non-debug", action="store_true", help="sign even when debug is off (only for a key that belongs to a test deployment)")

    crypto = sub.add_parser("crypto", help="encryption keys (needs ushka[crypto])")
    csub = crypto.add_subparsers(dest="crypto_command", metavar="<action>")
    csub.add_parser("genkey", help="print a new encryption key, for USHKA_CRYPTO_KEYS")

    docs = sub.add_parser("docs", help="check or preview Markdown docs (needs ushka[docs])")
    docsub = docs.add_subparsers(dest="docs_command", metavar="<action>")
    for name, help_text in (("check", "verify links, anchors and nav (exit 1 on problems)"),
                            ("serve", "preview the docs locally")):
        p = docsub.add_parser(name, help=help_text)
        p.add_argument("directory", nargs="?", default="docs", help="docs folder (default: docs)")
        p.add_argument("--api", default=None, help="package to document from docstrings")
        p.add_argument("--api-path", default=None, help="where that package lives (default: src/ or the import path)")
        if name == "serve":
            p.add_argument("--host", default="127.0.0.1")
            p.add_argument("--port", type=int, default=8001)

    i18n = sub.add_parser("i18n", help="translations: find messages and compile catalogs")
    isub = i18n.add_subparsers(dest="i18n_command", metavar="<action>")
    p = isub.add_parser("extract", help="find _() and {%% trans %%} messages and write the .pot template")
    p.add_argument("-o", "--output", default="", help="where to write it (default: <catalog_dir>/<domain>.pot)")
    isub.add_parser("compile", help="compile every .po in the catalog folder to .mo")

    routes = sub.add_parser("routes", help="list and manage filesystem routes")
    rsub = routes.add_subparsers(dest="routes_command", metavar="<action>")
    p = rsub.add_parser("list", help="list registered routes")
    p.add_argument("app", nargs="?", default="app:app", help="module:attribute (default: app:app)")
    p = rsub.add_parser("add", help="create a route file, e.g. /users/[user_id]")
    p.add_argument("path")
    p = rsub.add_parser("rm", help="remove a route file")
    p.add_argument("path")
    p = rsub.add_parser("mv", help="move/rename a route file")
    p.add_argument("old_path")
    p.add_argument("new_path")

    db = sub.add_parser("db", help="database migrations (needs ushka[orm])")
    dsub = db.add_subparsers(dest="db_command", metavar="<action>")
    dsub.add_parser("init", help="create the migrations folder")
    p = dsub.add_parser("make", help="generate a migration from model changes")
    p.add_argument("-m", "--message", default=None, help="description (auto-generated if omitted)")
    dsub.add_parser("migrate", help="apply pending migrations")
    p = dsub.add_parser("revert", help="revert migrations")
    p.add_argument("revision", nargs="?", default="-1", help="target ('-1' one step, 'base' all)")
    dsub.add_parser("history", help="show migration history")
    dsub.add_parser("status", help="show the current revision")
    p = dsub.add_parser("inspect", help="write Ushka models for an existing database")
    p.add_argument("--url", default=None, help="database URL (default: [database] url)")
    p.add_argument("--table", action="append", default=[], metavar="NAME", help="only this table (repeatable)")
    p.add_argument("--schema", default=None, help="database schema to read (default: the connection's)")
    p.add_argument("--write", default=None, metavar="FILE", help="write the models to FILE instead of stdout")
    p.add_argument("--force", action="store_true", help="overwrite FILE if it exists")
    p = dsub.add_parser("check-models", help="compare the app's models with the database (exit 1 on differences)")
    p.add_argument("--url", default=None, help="database URL (default: [database] url)")
    p.add_argument("--schema", default=None, help="database schema to read (default: the connection's)")
    p.add_argument("--models", action="append", default=[], metavar="MODULE", help="module that defines the models (default: app.models, models, app, main)")

    parser.set_defaults(_i18n=i18n, _routes=routes, _db=db, _docs=docs, _crypto=crypto)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point of the ``ushka`` command."""
    # Lets `app:app` and the routes/ modules import from the project directory.
    sys.path.insert(0, os.getcwd())
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "new":
        from ushka.cli.commands import new

        new.create_project(args.project_name)

    elif args.command in ("dev", "run"):
        from ushka.cli.commands.run import serve

        serve(args.app, args.host, args.port, dev=args.command == "dev")

    elif args.command == "check":
        from ushka.cli.commands.check import check

        if check(production=args.production):
            raise SystemExit(1)

    elif args.command == "config":
        from ushka.cli.commands.config import show

        if show(args.section, args.describe, args.template, args.markdown, args.all):
            raise SystemExit(1)

    elif args.command == "verify":
        from ushka.cli.commands.verify import verify

        if verify(args.app, args.include_writes, args.param, args.json, args.fail_on, args.skip_exempt, args.as_session, args.cookie, args.header):
            raise SystemExit(1)

    elif args.command == "session":
        from ushka.cli.commands.session import session

        if session(args.app, args.items, args.allow_non_debug):
            raise SystemExit(1)

    elif args.command == "crypto":
        if args.crypto_command == "genkey":
            from ushka.cli.commands.crypto import genkey

            if genkey():
                raise SystemExit(1)
        else:
            args._crypto.print_help()

    elif args.command == "docs":
        from ushka.cli.commands import docs as docs_command

        if args.docs_command == "check":
            if docs_command.check(args.directory, args.api, args.api_path):
                raise SystemExit(1)
        elif args.docs_command == "serve":
            docs_command.serve(args.directory, args.api, args.api_path, args.host, args.port)
        else:
            args._docs.print_help()

    elif args.command == "i18n":
        from ushka.cli.commands import i18n as i18n_command

        if args.i18n_command == "extract":
            i18n_command.extract(args.output)
        elif args.i18n_command == "compile":
            if i18n_command.compile_catalogs():
                raise SystemExit(1)
        else:
            args._i18n.print_help()

    elif args.command == "routes":
        from ushka.cli.commands import routes

        action = args.routes_command
        if action == "list":
            routes.list_routes(args.app)
        elif action == "add":
            routes.add_route(args.path)
        elif action == "rm":
            routes.remove_route(args.path)
        elif action == "mv":
            routes.move_route(args.old_path, args.new_path)
        else:
            args._routes.print_help()

    elif args.command == "db":
        if not args.db_command:
            args._db.print_help()
            return
        db = _load_db_command()
        action = args.db_command
        if action == "make":
            db.make(args.message)
        elif action == "revert":
            db.revert(args.revision)
        elif action == "inspect":
            db.inspect(args.url, args.table, args.schema, args.write, args.force)
        elif action == "check-models":
            if db.check_models(args.url, args.schema, args.models):
                raise SystemExit(1)
        else:
            getattr(db, action)()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
