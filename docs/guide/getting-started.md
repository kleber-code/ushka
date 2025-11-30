# Getting Started

## Installation

Ushka is available on PyPI and can be installed with pip:

```bash
pip install ushka
```

## Running Your First App

Ushka is designed to be simple. Here's how you can get a "Hello, World" app running.

### 1. Project Structure

Create a folder for your project. Ushka expects a `routes` directory for file-based routing.

```text
my_project/
├── app.py
└── routes/
    └── index.py
```

### 2. Create a Route

Create a file `routes/index.py`. The name of the function inside this file will correspond to the HTTP method.

```python
# in routes/index.py

# Responds to GET /
def get():
    return "<h1>Hello, World!</h1>"
```

### 3. Create the App

Create a file `app.py` to initialize and run your Ushka application.

```python
# in app.py
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

The first time you run the app, Ushka will create a `ushka.toml` file for you with default configurations.

### 4. Run the App

```bash
python app.py
```

You should see a startup banner in your terminal with a table of all discovered routes. You can now visit `http://127.0.0.1:8000` in your browser.