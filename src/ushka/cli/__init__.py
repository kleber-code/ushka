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

    parser.set_defaults(_routes=routes, _db=db)
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
        else:
            getattr(db, action)()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
