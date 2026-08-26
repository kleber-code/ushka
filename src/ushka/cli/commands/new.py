"""
This module provides the Command Line Interface (CLI) command for creating
a new Ushka project with a default directory structure and essential files.

Commands
--------
create_project: Initializes a new Ushka project.
"""

import os
import tomlkit


def create_project(project_name: str):
    """Creates a new Ushka project with a default structure.

    This function sets up the necessary directories (`routes`, `static`, `templates`)
    and creates initial files (`app.py`, `config.toml`, `routes/index.py`,
    `templates/index.html`) to provide a basic, runnable Ushka application.
    If a directory with the specified `project_name` already exists, the creation
    process is aborted.

    Parameters
    ----------
    project_name : str
        The name of the new project to create. This will also be the name of
        the root directory for the project.
    """
    if os.path.exists(project_name):
        print(f"❌ Directory '{project_name}' already exists.")
        return

    print(f"🚀 Creating new Ushka project: {project_name}")

    # Create project directory
    os.makedirs(project_name)

    # Create subdirectories
    os.makedirs(os.path.join(project_name, "routes"))
    os.makedirs(os.path.join(project_name, "static"))
    os.makedirs(os.path.join(project_name, "templates"))

    # Create app.py
    # `Ushka` takes no arguments: it discovers its own working directory and
    # loads `ushka.toml` from there.
    with open(os.path.join(project_name, "app.py"), "w") as f:
        f.write(
            """from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
"""
        )

    # Create ushka.toml
    # This is the file `Config` actually reads; any key left out here is filled
    # in with its default on the first run.
    config_data = {
        "app": {"name": project_name, "debug": True},
        "database": {"url": f"sqlite+aiosqlite:///{project_name}.db"},
    }
    with open(os.path.join(project_name, "ushka.toml"), "w") as f:
        f.write(tomlkit.dumps(config_data))

    # Create routes/index.py
    with open(os.path.join(project_name, "routes", "index.py"), "w") as f:
        f.write(
            """from ushka.http.request import Request
from ushka.templating import render

async def get(request: Request):
    return await render(request, "index.html", {"message": "Welcome to Ushka!"})
"""
        )

    # Create templates/index.html
    with open(os.path.join(project_name, "templates", "index.html"), "w") as f:
        f.write(
            """<!DOCTYPE html>
<html>
<head>
    <title>{{ request.app.config.APP_NAME }}</title>
</head>
<body>
    <h1>{{ message }}</h1>
</body>
</html>
"""
        )

    print(f"✅ Project '{project_name}' created successfully!")
    print("\nTo get started:")
    print(f"  cd {project_name}")
    print("  ushka dev")
