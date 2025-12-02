import os
import tomlkit

def create_project(project_name: str):
    """
    Creates a new Ushka project with a default structure.
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
    with open(os.path.join(project_name, "app.py"), "w") as f:
        f.write(
            """from ushka import Ushka
from ushka.core.config import Config

config = Config()
app = Ushka(config=config)
"""
        )

    # Create config.toml
    config_data = {
        "APP_NAME": project_name,
        "DEBUG": True,
        "database": {"URL": f"sqlite+aiosqlite:///{project_name}.db"},
    }
    with open(os.path.join(project_name, "config.toml"), "w") as f:
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
    <title>{{ APP_NAME }}</title>
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
    print("  ushka server")
