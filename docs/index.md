<div style="text-align: center; padding: 4rem 0;">
  <div style="font-family: 'JetBrains Mono', monospace; font-size: 5rem; margin-bottom: 1rem; white-space: nowrap;">(¬‿¬)</div>
  <h1 style="font-size: 3rem; font-weight: bold; margin-bottom: 1rem;">Ushka Framework: My Grand Entrance</h1>
  <p style="font-size: 1.5rem; margin-bottom: 2rem;">Making Python development *tolerable*. The most efficient, elegant, and frankly, *charming* web framework for your Python endeavors. You're welcome.</p>
  <p>
    <a href="/ushka/guide/getting-started/" class="md-button md-button--primary">Get Started (If You Dare)</a>
    <a href="/ushka/guide/introduction/" class="md-button">Admire the Documentation</a>
  </p>
</div>

---

## Why Choose Me? (The Obvious Reasons)

Tired of frameworks designed by committee? I bring joy back to backend development. I effortlessly transform your filesystem into an API, manage your server (because you shouldn't have to), and if you manage to break something (which, let's be honest, you probably will), I present you with an error page so stunning, you might just frame it.

<div class="grid cards" markdown>

-  :material-folder-file-outline: __File-Based Routing__
   Effortlessly turn your mundane file structure into dazzling API endpoints. It's almost like magic, but better.

-  :material-code-json: __Decorator Routing__
   Prefer explicit declarations? Define your routes with my elegant decorators. I cater to all tastes.

-  :material-palette-outline: __Visual DX__
   Indulge in my colorful, meticulously organized, and incredibly informative terminal logs. Because even debugging should be beautiful.

-  :material-bug: __Ushka Panic!__
   Interactive error pages with full stack traces and local variable inspection. I make your mistakes look good.

-  :material-hammer-wrench: __Zero Config__
   Run your app with minimal fuss. I handle the boilerplate. You're welcome.

-  :material-injection: __Dependency Injection__
   Automatically inject Request objects and URL parameters. I make your functions smarter, without them even realizing it.

</div>

---

## Acquisition (It's Quite Simple, Really)

Install me with pip. If you can't manage this, I question your life choices.

```bash
pip install ushka
```

---

## A Glimpse of My Brilliance: Quick Start (File-Based)

Create `app.py`:

```python
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

Create `routes/index.py`:

```python
# Responds to GET / with a polite nod.
def get():
    return {"message": "Hello, Ushka! (UwU)"}
```

Then, with a flourish, run your app:

```bash
python app.py
```
Visit `http://127.0.0.1:8000` in your browser. Marvel at my efficiency.

---

## Visual Spectacle: The Ushka Panic!

Debugging doesn't have to be a descent into madness. My Panic Mode is here to guide you with a knowing smirk.

*   👀 **Inspect local variables:** Uncover the secrets of your code.
*   📋 **Copy the error:** One elegant click to share with your chosen oracle (or StackOverflow/ChatGPT).
*   🌙 **Dark theme:** Because even in moments of despair, aesthetics are paramount.

---

## Further Adoration (Resources)

- [My Glorious Documentation](/ushka/guide/introduction/)
- [My Presence on PyPI](https://pypi.org/project/ushka/)
- [My GitHub Repository (Where the Magic Lives)](https://github.com/kleber-code/ushka)