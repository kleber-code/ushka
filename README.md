# 🐱 Ushka Framework

[![PyPI Version](https://img.shields.io/pypi/v/ushka)](https://pypi.org/project/ushka/)
![Python Versions](https://img.shields.io/pypi/pyversions/ushka)
![License](https://img.shields.io/pypi/l/ushka)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Make Python Cute Again.** > The most beautiful, agile, and visually striking web framework you'll use in your terminal.

---

## 👋 Hi, I'm Ushka!

Tired of frameworks that give you a white screen of death and boring black-and-white logs? **Ushka** was born from the idea that backend coding doesn't have to be ugly or bureaucratic.

I turn your filesystem into an API automatically, I configure the server myself, and if something goes wrong, I show you a **Cyberpunk** error page so pretty you'll want to leave the bug there.

### ✨ Why use me?

* **🎨 Visual DX:** My terminal logs are colorful (Neon/Dark theme), organized, and informative.
* **📂 File-Based Routing:** Stop manually importing controllers. Create a file in the `routes/` folder and the magic happens.
* **✍️ Decorator Routing:** For those who prefer explicitness, declare routes with decorators, just like in Flask or FastAPI.
* **🧠 Zero Config:** The first time you run me, I generate `ushka.toml` for you. No boilerplate.
* **🛡️ Panic Mode:** My interactive error page lets you copy the traceback with one click and inspect local variables.

---

## ✅ What's ready? (Features)

Ushka is evolving fast. Here is what is **running smoothly** in the current version:

* ✅ **Dual Routing System:**
    * **Auto-Discovery:** Automatic route mapping based on the `routes/` folder.
    * **Decorator-Based:** Explicitly define routes with `@app.get()`, `@app.post()`, etc.
* ✅ **Smart `Request` Object:** Access `headers`, `query`, `body`, `json`, and `form` data as properties. Data is loaded lazily on first access.
* ✅ **Flexible `Response`:** Return a `dict` (for JSON), `str` (for HTML), or a complete `Response` object for full control.
* ✅ **Jinja2 Templates:** Native support with a simple `render()` function.
* ✅ **Ushka Panic:** Stylized error handling (500/404) with dark theme, interactive stacktrace, and code highlighting.
* ✅ **Auto Config:** Automatic generation and reading of `ushka.toml`.
* ✅ **Rich Logging:** Request logs colored by status code (Success=Green, Error=Red, Redirect=Blue).
* ✅ **Dependency Injection:** Automatically inject the `Request` object and dynamic URL parameters into your route functions just by type-hinting them.
* ✅ **Core ASGI:** Based on Uvicorn, fully async.

---

## 📦 Installation

```bash
pip install ushka
````

-----

## 🚀 How to use (No fluff)

Ushka offers two ways to build your API. Choose one or mix them!

### Method 1: File-Based Routing (The Classic)

This method follows the "Convention over Configuration" philosophy.

**1. The Structure:**
```text
my_project/
├── app.py              # Where it all starts
├── ushka.toml          # I create this for you automatically!
└── routes/             # Your Routes (The Magic)
    ├── index.py        # Route: /
    └── users/
        └── [id].py     # Route: /users/<id>
```

**2. The Route (`routes/index.py`):**

The function name becomes the HTTP Method.
```python
# Responds to GET /
def get():
    return "<h1>Hello, World!</h1>"
```

**3. The App (`app.py`):**
```python
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    # Host and port are loaded from ushka.toml
    app.run()
```

### Method 2: Decorator-Based Routing (The Explicit)

Prefer to see your routes in one place? Use decorators.

**1. The App (`app.py`):**
```python
from ushka import Ushka, Request

app = Ushka()

# Responds to GET /
@app.get("/")
def index():
    return "<h1>Hello from a decorator!</h1>"

# Responds to POST /users
@app.post("/users")
async def create_user(request: Request):
    user_data = await request.json()
    return {"status": "created", "user": user_data}

if __name__ == "__main__":
    app.run()
```

### Run it!

```bash
python app.py
```
Look at your terminal. Appreciate the banner. See the route table.
Now go to `http://127.0.0.1:8000`.

-----

## 🖼️ Visual Showcase

### The "Ushka Panic" (Debug Page)

We believe that making mistakes is part of the process, but debugging should be easy.

  * Inspect local variables.
  * Copy the error with one click to paste into StackOverflow/ChatGPT.
  * Dark theme so you don't burn your eyes at 3 AM.

![Ushka Panic Screenshot](src/ushka/internal/assets/ushka_panic.png)

-----

## 🗺️ Roadmap (What's coming next)

We are currently in **Alpha**, but we dream big. The plan for World Domination (v1.0):

  * [ ] **Ushka CLI:** `ushka new` commands to scaffold projects and `ushka deploy` for auto-HTTPS configuration (Caddy).
  * [ ] **Multipart Streaming:** Support for large file uploads without eating up RAM.
  * [ ] **Middlewares:** Robust system to intercept requests.
  * [ ] **Cookies & Sessions:** Native state management.
  * [ ] **Subapps (Blueprints):** For when your project gets huge.
  * [ ] **Auth Embedded:** Optional built-in login system.

-----

## 🤝 Contributing

Ushka is open-source and made with love. Spotted a bug? Want to request a feature? Open an Issue!

  * **License:** MIT
  * **Author:** Kleber Code

-----

*Made with ❤️, Python, and lots of caffeine.*
