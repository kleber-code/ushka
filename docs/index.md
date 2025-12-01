<div style="text-align: center; padding: 4rem 0;">
  <div style="font-family: 'JetBrains Mono', monospace; font-size: 5rem; margin-bottom: 1rem;">/ᐠ - ˕ -マ Ⳋ</div>
  <h1 style="font-size: 3rem; font-weight: bold; margin-bottom: 1rem;">Ushka Framework</h1>
  <p style="font-size: 1.5rem; margin-bottom: 2rem;">Make Python Cute Again. The beautiful, agile, and visually striking web framework.</p>
  <p>
    <a href="/ushka/guide/getting-started/" class="md-button md-button--primary">Get Started</a>
    <a href="/ushka/guide/introduction/" class="md-button">Documentation</a>
  </p>
</div>

---

## ✨ Why Ushka?

Tired of frameworks that feel bland and bureaucratic? Ushka brings joy back to backend development. We turn your filesystem into an API automatically, configure your server, and if something goes wrong, we show you a **Cute** error page so pretty you'll want to leave the bug there.

<div class="grid cards" markdown>

-  :material-folder-file-outline: __File-Based Routing__
   Effortlessly turn your file structure into API endpoints.

-  :material-code-json: __Decorator Routing__
   Prefer explicit routes? Define them with simple decorators.

-  :material-palette-outline: __Visual DX__
   Enjoy colorful, organized, and informative terminal logs.

-  :material-bug: __Panic Mode__
   Interactive error pages with stack traces and local variable inspection.

-  :material-hammer-wrench: __Zero Config__
   Run your app with minimal setup, Ushka handles the boilerplate.

-  :material-injection: __Dependency Injection__
   Automatically inject Request objects and URL parameters.

</div>

---

## 📦 Installation

Install Ushka with pip:

```bash
pip install ushka
```

---

## 🚀 Quick Start (File-Based)

Create `app.py`:

```python
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

Create `routes/index.py`:

```python
# Responds to GET /
def get():
    return {"message": "Hello, Ushka!"}
```

Then run your app:

```bash
python app.py
```
Visit `http://127.0.0.1:8000` in your browser!

---

## 🖼️ Visual Showcase: Ushka Panic!

Debugging doesn't have to be dreadful. Ushka's Panic Mode provides:
- Inspection of local variables.
- One-click error copying for quick sharing.
- A dark theme to save your eyes at 3 AM.

---

## 📚 More Resources

- [Full Documentation](/ushka/guide/introduction/)
- [View on PyPI](https://pypi.org/project/ushka/)
- [GitHub Repository](https://github.com/kleber-code/ushka)
