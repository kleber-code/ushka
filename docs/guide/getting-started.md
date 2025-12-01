# 🚀 Getting Started: Your First Ushka App! 🐾

Ready to dive in? Getting your first Ushka app up and running is surprisingly straightforward. We've tried to keep the setup as minimal as possible.

## 📦 Installation: A Quick `pip install`!

Ushka is available on PyPI. Install it like any other self-respecting Python package:

```bash
pip install ushka
```

## 🌐 Running Your First App: Hello, World (and then some)!

Ushka's designed for simplicity. Here's how to get a basic "Hello, World" app purring along.

### 1. Project Structure: Keep it Tidy! 📂

Create a folder for your project. Ushka expects a `routes` directory for its file-based routing. It's not optional.

```text
my_project/
├── app.py
└── routes/
    └── index.py
```

### 2. Create a Route: Your App's First Greeting! 👋

In `routes/index.py`, define a function. Its name should correspond to the HTTP method.

```python
# in routes/index.py

# Responds to GET /
def get():
    return "<h1>Hello, World from Ushka!</h1>" # A classic for a reason.
```

### 3. Create the App: The Grand Orchestrator! 🎶

Now, create `app.py` to initialize and run your Ushka application.

```python
# in app.py
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

The first time you run the app, Ushka will be a good host and create a `ushka.toml` file for you with default configurations. No manual setup required for that.

### 4. Run the App: Showtime! 🎬

Open your terminal in your project's folder and execute:

```bash
python app.py
```

You should see Ushka's startup banner (we think it's pretty neat) and a table of all discovered routes. Now, point your browser to `http://127.0.0.1:8000`. Congratulations, you've officially made Python cuter! (And launched an app.) 💖