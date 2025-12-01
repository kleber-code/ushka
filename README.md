# 💖 Ushka Framework: Make Python Cute Again! 🎀

[![PyPI Version](https://img.shields.io/pypi/v/ushka)](https://pypi.org/project/ushka/)
[![Documentation](https://img.shields.io/badge/Documentation-View%20Here-orange)](https://kleber-code.github.io/ushka/)
![Python Versions](https://img.shields.io/pypi/pyversions/ushka)
![License](https://img.shields.io/pypi/l/ushka)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> ✨ **MINIMALIST ABOVE EVERYONE, CUTE ABOVE EVERYTHING.** ✨
> The most adorable, agile, and visually captivating web framework for your Python adventures!

---

## 🐾 Hello, Lovely Coder! I'm Ushka!

Are you tired of web frameworks that feel... well, a bit *boring*? 😴 Black-and-white logs, endless configurations, and error pages that make you want to curl up and cry? 😭

💖 Ushka believes backend coding should be a joyous, beautiful experience! I transform the mundane into the magical, turning complex tasks into simple, delightful moments.

### 🌟 Why choose little old me? (Ushka's Sweet Perks!)

*   **🎨 Visual Delight:** My terminal logs are a pastel dream! Minimalist, organized, and bursting with helpful colors.
*   **📂 File-Based Routing: Pure Magic!** ✨
    Forget wrestling with imports. Just create a file in your `routes/` folder, and *poof*! Your API endpoint is ready to charm.
*   **✍️ Decorator Routing: Elegantly Expressive!**
    For those who love a clear declaration, define your routes with cute little decorators, just like hugging your code!
*   **🧠 Zero Config: Instant Cuddles!**
    Run me for the first time, and I'll lovingly craft an `ushka.toml` just for you. No fuss, just fun!
*   **🛡️ Ushka Panic: The Cutest Errors!**
    Oopsie! A bug? My interactive error page is so darling, you might just fall in love with debugging! Copy tracebacks, inspect variables – all with a friendly smile.

---

## 📚 Peek at the Docs!

This README is just a tiny hug! For a deeper dive into Ushka's heart, including tutorials, guides, and a full API reference, flutter over to our **[full documentation here](https://kleber-code.github.io/ushka/)**.

---

## ✅ What Ushka does best! (Tiny but Mighty Features!)

Ushka is always growing with love! Here's what's purring smoothly in the current version:

*   ✅ **Dual Routing System: Double the Cuteness!**
    *   **Auto-Discovery:** Automatic route mapping just by creating files in `routes/`.
    *   **Decorator-Based:** Explicitly define routes with `@app.get()`, `@app.post()`, etc.
*   ✅ **Smart `Request` Object: Clever & Cozy!**
    Access `headers`, `query`, `body`, `json`, and `form` data effortlessly. Data loads lazily, just when you need a little peek!
*   ✅ **Flexible `Response`: Your Way, Always!**
    Return a `dict` (for yummy JSON), a `str` (for snuggly HTML), or a full `Response` object for ultimate control!
*   ✅ **Jinja2 Templates: Warm & Fuzzy!**
    Native support with a simple `render()` function to make your pages sparkle.
*   ✅ **Ushka Panic: Debugging is a Breeze!**
    Stylized error handling (500/404) with a cozy dark theme, interactive stacktrace, and super clear code highlighting.
*   ✅ **Auto Config: Set & Forget!**
    Automatic generation and gentle reading of `ushka.toml`.
*   ✅ **Rich Logging: A Symphony of Colors!**
    Request logs adorned with colors for every status code (Success=Green, Error=Red, Redirect=Blue).
*   ✅ **Dependency Injection: Smart Helpers!**
    Automatically inject the `Request` object and dynamic URL parameters into your route functions with just a type-hint. So clever!
*   ✅ **Core ASGI: Speedy & Sweet!**
    Built on Uvicorn, fully asynchronous for a zippy, happy experience.

---

## 📦 Install Ushka (It's a Cinch!)

Getting started is as easy as a gentle purr!

```bash
pip install ushka
````

-----

## 🚀 How to Play with Ushka! (Super Simple Steps!)

Ushka offers two delightful ways to build your API. Pick your favorite or mix them up!

### Method 1: File-Based Routing (The Classic Cuddle!)

This method embraces "Convention over Configuration" with a warm hug!

**1. Your Project's Cozy Nook:**
```text
my_project/
├── app.py              # Where all the magic begins!
├── ushka.toml          # Ushka lovingly creates this for you!
└── routes/             # Your delightful Routes (Pure enchantment!)
    ├── index.py        # Route: /
    └── users/
        └── [id].py     # Route: /users/<id>
```

**2. Your First Charming Route (`routes/index.py`):**

The function name sweetly becomes your HTTP Method!
```python
# Responds to GET / with a little wave!
def get():
    return "<h1>Hello, World from Ushka! 💖</h1>"
```

**3. Your Little App (`app.py`):**
```python
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    # Host and port are loaded from your cozy ushka.toml
    app.run()
```

### Method 2: Decorator-Based Routing (The Explicit Embrace!)

Prefer to see all your routes in one happy place? Decorators are your best friend!

**1. Your Little App (`app.py`):**
```python
from ushka import Ushka, Request

app = Ushka()

# Responds to GET / with a cheerful greeting!
@app.get("/")
def index():
    return "<h1>Hello from a decorator, with love!</h1>"

# Responds to POST /users with a warm welcome!
@app.post("/users")
async def create_user(request: Request):
    user_data = await request.json()
    return {"status": "created", "user": user_data}

if __name__ == "__main__":
    app.run()
```

### Run it! (So exciting!)

```bash
python app.py
```
Peep at your terminal! Admire the adorable banner. See your neat route table.
Now, dash over to `http://127.0.0.1:8000` and feel the cuteness!

-----

## 🖼️ A Glimpse of Cuteness! (Visual Showcase)

### The "Ushka Panic" (Your Debugging Buddy!)

We know little accidents happen, but debugging shouldn't be a scary monster! Ushka Panic is here to help with a smile.

*   👀 **Inspect local variables:** Peek at what's happening behind the scenes!
*   📋 **Copy the error:** One tiny click to share with your friends (or StackOverflow/ChatGPT)!
*   🌙 **Dark theme:** So your eyes stay cozy even during late-night coding cuddles!

![Ushka Panic Screenshot](src/ushka/internal/assets/ushka_panic.png)

-----

## 🤝 Join Our Cozy Community!

Ushka is made with so much ❤️. Spotted a teeny bug? Have a sweet feature idea? Please, open an Issue!

*   **License:** MIT
*   **Author:** Kleber Code (kleber-code)

-----

*Made with an abundance of ❤️, Python magic, and endless purrs.*