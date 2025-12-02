# Getting Started: Let's Make Some Magic

Alright, enough talk. Let's get our hands dirty. I'm going to show you how easy it is to get started with me. And I do mean *easy*.

## Installation: The Hardest Part (Just Kidding)

I'm on PyPI, of course. You can install me with a simple `pip install`. If you can't handle that, we might have a problem.

```bash
pip install ushka
```

## Your First App: A Masterpiece in the Making

We're going to build a "Hello, World" app. I know, I know, it's a cliché. But it's a classic for a reason. It's the first step on a long and beautiful journey. Or something like that.

### 1. The Sacred Project Structure

First, create a folder for your project. I'm not picky, but I do have one rule: you need a `routes` directory. That's where the magic happens.

```text
my_project/
├── app.py
└── routes/
    └── index.py
```

### 2. Your First Masterpiece: The Route

In `routes/index.py`, you're going to write a function. This function will be your first route. The name of the function determines the HTTP method. Simple, right?

```python
# in routes/index.py

# This little guy responds to GET /
def get():
    return "<h1>Behold, my magnificent creation!</h1>"
```

### 3. The Grand Finale: The App

Now, in `app.py`, you'll create an instance of me and run it. This is where it all comes together.

```python
# in app.py
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

The first time you run this, I'll create a `ushka.toml` file for you. It's my little welcome gift. It has all the default configurations you'll need. You don't have to lift a finger.

### 4. Showtime!

Open your terminal, navigate to your project's folder, and run:

```bash
python app.py
```

You'll see my beautiful startup banner (I'm very proud of it) and a table of all the routes I've discovered. Now, open your browser and go to `http://127.0.0.1:8000`. You've just created a web app. You're welcome.

## Serving Static Files: Because We're Not Savages

Need to serve static files like CSS, JavaScript, or images? Of course you do. I'm not going to make you jump through hoops for that.

1.  **Create a `static` directory** in your project's root:

    ```text
    my_project/
    ├── app.py
    ├── routes/
    │   └── index.py
    └── static/
        └── style.css
    ```

2.  **I'll automatically serve** any files in that directory under the `/static` path. So, `static/style.css` will be available at `http://127.0.0.1:8000/static/style.css`.

It's that simple. I know, I'm amazing. OwO
