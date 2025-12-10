# Command-Line Interface (CLI)

Ushka comes with a handy command-line interface (CLI) to help you with common development tasks. You can access it through the `ushka` command.

<!-- termynal -->
```bash
$ ushka --help
Usage: ushka [OPTIONS] COMMAND [ARGS]...

  Ushka CLI

Options:
  --help  Show this message and exit.

Commands:
  db      Database commands
  dev     Starts the development server with auto-reload
  new     Creates a new Ushka project
  routes  Route management
  run     Starts the production server

$ ushka new my_awesome_project
🚀 Creating new Ushka project: my_awesome_project
✅ Project 'my_awesome_project' created successfully!

$ cd my_awesome_project
$ ushka dev
INFO: Starting Ushka server in development mode on http://127.0.0.1:8000
INFO: Auto-reload is enabled.
```

## Creating a New Project

The `new` command is the easiest way to start a new Ushka project. It creates a new directory with a recommended project structure, including a sample application, configuration file, and templates.

```bash
ushka new my_project
```

This will create a `my_project` directory with everything you need to get started.

## Development Server (`dev`)

The `dev` command starts the development server. This command is designed for local development and includes features like auto-reloading when you change your code.

```bash
ushka dev
```

This will start a Uvicorn server on `http://127.0.0.1:8000` with auto-reload enabled.

### Server Options

*   `--host`: The host to bind to. Defaults to `127.0.0.1`.
*   `--port`: The port to listen on. Defaults to `8000`.

Example:

```bash
ushka dev --host 0.0.0.0 --port 5000
```

## Production Server (`run`)

The `run` command starts the server in production mode. This command is optimized for performance and does not include auto-reloading.

```bash
ushka run
```

You can use the `--host` and `--port` options to configure the server, just like with the `dev` command. It's recommended to configure the number of workers in your `config.toml` file for production use.

## Route Management

The `routes` command provides a set of tools for managing your application's routes.

### `routes list`

Lists all the registered routes in your application. This is useful for debugging and for getting an overview of your application's endpoints.

```bash
ushka routes list
```

### `routes add`

Creates a new route file with a basic `get` function.

```bash
ushka routes add /users/profile
```

This will create the file `routes/users/profile.py`.

### `routes rm`

Removes a route file.

```bash
ushka routes rm /users/profile
```

This will delete the file `routes/users/profile.py`.

### `routes mv`

Moves or renames a route file.

```bash
ushka routes mv /users/profile /account/settings
```

This will move the file `routes/users/profile.py` to `routes/account/settings.py`.


## Database Migrations

Ushka provides a set of commands to help you manage your database schema using Alembic.

### `db init`

This command initializes the migrations environment. It creates a `migrations` directory and an `alembic.ini` file in your project.

```bash
ushka db init
```

### `db make`

Once you've made changes to your models (e.g., added a new column), you can use the `make` command to automatically generate a new migration script.

```bash
ushka db make "Add a bio column to the user model"
```

### `db migrate`

This command applies all pending migrations to your database.

```bash
ushka db migrate
```

### `db revert`

If you need to undo a migration, you can use the `revert` command. By default, it will revert the last migration.

```bash
ushka db revert
```

### `db status`

This command shows the current revision of your database.

```bash
ushka db status
```

### `db history`

This command shows the full migration history.

```bash
ushka db history
```

> **Ushka Tip:** Database migrations are a powerful tool for managing changes to your database schema over time. It's a good practice to create a new migration for every change you make to your models. This makes it easy to track changes and to collaborate with other developers.
