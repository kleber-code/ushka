# ushka/cli.py
import argparse
import os
import sys

from ushka.cli.commands import db, dev, new, routes, run


def main():
    # Adds the current directory to the Python PATH.
    # This is CRITICAL: it allows importing the user's 'app.py' where the command is run.
    sys.path.insert(0, os.getcwd())

    parser = argparse.ArgumentParser(description="Ushka Framework CLI", prog="ushka")

    # Main subcommands (run, db, etc)
    subparsers = parser.add_subparsers(dest="command", help="Available command")

    # --- COMMAND: NEW ---
    parser_new = subparsers.add_parser("new", help="Creates a new Ushka project")
    parser_new.add_argument("project_name", help="The name of the project to create")

    # --- COMMAND: ROUTES ---
    parser_routes = subparsers.add_parser("routes", help="Route management")
    routes_subparsers = parser_routes.add_subparsers(
        dest="routes_command", help="Route actions"
    )

    # ushka routes list
    parser_routes_list = routes_subparsers.add_parser(
        "list", help="Lists all registered routes"
    )
    parser_routes_list.add_argument(
        "app", help="Path to the app (e.g., app:app)", nargs="?", default="app:app"
    )

    # ushka routes add <path>
    parser_routes_add = routes_subparsers.add_parser(
        "add", help="Creates a new route file"
    )
    parser_routes_add.add_argument("path", help="The URL path of the route to create")

    # ushka routes rm <path>
    parser_routes_rm = routes_subparsers.add_parser(
        "rm", help="Removes a route file"
    )
    parser_routes_rm.add_argument("path", help="The URL path of the route to remove")

    # ushka routes mv <old_path> <new_path>
    parser_routes_mv = routes_subparsers.add_parser(
        "mv", help="Moves or renames a route file"
    )
    parser_routes_mv.add_argument("old_path", help="The current URL path of the route")
    parser_routes_mv.add_argument("new_path", help="The new URL path for the route")

    # --- COMMAND: DEV ---
    parser_dev = subparsers.add_parser(
        "dev", help="Starts the development server with auto-reload"
    )
    parser_dev.add_argument(
        "app", help="Path to the app (e.g., app:app)", nargs="?", default="app:app"
    )
    parser_dev.add_argument("--host", default="", help="Server host")
    parser_dev.add_argument("--port", type=int, default=0, help="Server port")

    # --- COMMAND: RUN ---
    parser_run = subparsers.add_parser(
        "run", help="Starts the production server"
    )
    parser_run.add_argument(
        "app", help="Path to the app (e.g., app:app)", nargs="?", default="app:app"
    )
    parser_run.add_argument("--host", default="", help="Server host")
    parser_run.add_argument("--port", type=int, default=0, help="Server port")

    # --- COMMAND: DB ---
    # Ex: ushka db init
    parser_db = subparsers.add_parser("db", help="Database Management")
    db_subparsers = parser_db.add_subparsers(dest="db_command", help="Database actions")

    # ushka db init
    db_subparsers.add_parser("init", help="Initializes the migrations structure")

    # ushka db make [-m "message"]
    parser_make = db_subparsers.add_parser("make", help="Creates a new migration")
    parser_make.add_argument(
        "-m",
        "--message",
        help="Description of the change (optional - auto-generated if omitted)",
        default=None,
    )

    # ushka db migrate
    db_subparsers.add_parser("migrate", help="Applies pending migrations")

    # ushka db revert [revision]
    parser_revert = db_subparsers.add_parser(
        "revert", help="Revert database migrations"
    )
    parser_revert.add_argument(
        "revision",
        nargs="?",
        default="-1",
        help="Revision to revert to (default: '-1' for one step back, use 'base' to undo all)",
    )

    # ushka db history
    db_subparsers.add_parser("history", help="Show migration history")

    # ushka db status
    db_subparsers.add_parser("status", help="Show current database revision")

    # --- DISPATCH ---
    args = parser.parse_args()

    if args.command == "new":
        new.create_project(args.project_name)

    elif args.command == "routes":
        if args.routes_command == "list":
            routes.list_routes(args.app)
        elif args.routes_command == "add":
            routes.add_route(args.path)
        elif args.routes_command == "rm":
            routes.remove_route(args.path)
        elif args.routes_command == "mv":
            routes.move_route(args.old_path, args.new_path)
        else:
            parser_routes.print_help()

    elif args.command == "dev":
        dev.run(args.app, args.host, args.port)

    elif args.command == "run":
        run.run(args.app, args.host, args.port)

    elif args.command == "db":
        if args.db_command == "init":
            db.init()
        elif args.db_command == "make":
            db.make(args.message)
        elif args.db_command == "migrate":
            db.migrate()
        elif args.db_command == "revert":
            db.revert(args.revision)
        elif args.db_command == "history":
            db.history()
        elif args.db_command == "status":
            db.status()
        else:
            parser_db.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()