# Ushka

[](https://www.google.com/search?q=https://pypi.org/project/ushka/)
[](https://www.google.com/search?q=https://travis-ci.com/your_username/ushka)
[](https://opensource.org/licenses/MIT)

Ushka is a minimal, experimental Python micro-framework for hobbyists and solo developers. Its goal is to enable rapid API development with **zero boilerplate** by using file-based routing.

No decorators, no complex configuration. Just create a file in the `routes/` directory, and it becomes an API endpoint.

## ⚠️ Alpha Stage: Not Production Ready

This is an **early alpha release**. The project is in active, unstable development.

  * The API **will** change frequently without warning.
  * It is **not suitable for production use**.
  * It is intended for experimentation and feedback only.

## Philosophy

  * **File-Based Routing:** The filesystem is the API.
  * **Zero Boilerplate:** No decorators, no manual route registration.
  * **Get Out of the Way:** The framework should be invisible.
  * **Built for One:** Designed for the speed and simplicity a solo dev needs.

-----

## Core Alpha Feature: File-Based Routing

This is the only major feature implemented in the current alpha.

You don't need to import `app` or use decorators. Ushka scans the `routes/` directory and maps file and function names directly to HTTP routes.

The name of the `.py` file determines the URL path, and the function names (`get`, `post`, `put`, `delete`) map to the HTTP methods.

### Example

Create a file named `routes/hello.py`:

```python
# routes/hello.py

# This function automatically becomes:
# GET /hello
def get():
    return {"message": "Hello from Ushka!"}

# This function automatically becomes:
# POST /hello
def post():
    # Ushka will provide request data (form, json) as arguments
    # (Note: This part of the API is still unstable)
    return {"message": "You posted data"}, 201
```

That's it. No other code is needed.

-----

## How to Run (Alpha Test)

1.  **Install it:**

    ```bash
    pip install ushka
    ```

2.  **Create your project:**

    ```bash
    mkdir my_test_app
    cd my_test_app
    mkdir routes
    ```

3.  **Create your entry file `app.py`:**

    ```python
    # app.py
    from ushka import Ushka

    # This is all you need.
    # Ushka will find the 'routes/' folder.
    app = Ushka()
    ```

4.  **Create your first route `routes/hello.py`:**

    ```python
    # routes/hello.py
    def get():
        return {"message": "It works!"}
    ```

5.  **Run the dev server:**

    ```bash
    ushka run
    ```

    *(Note: The `ushka run` command assumes your file is named `app.py`)*

6.  **Test it:**

    ```bash
    curl http://127.0.0.1:8000/hello
    ```

    **Response:** `{"message": "It works!"}`

-----

## Roadmap (Moving from Alpha to Beta)

The current alpha is minimal. Here is the plan to make it useful:

1.  **Stabilize the Router:** Finalize API for dynamic routes (e.g., `routes/users/[id].py`).
2.  **Request Object:** Create a simple, clean `Request` object (for headers, queries, etc.).
3.  **Response Object:** Create a `Response` object for setting status codes and headers easily.
4.  **File-Based Middleware:** Add support for `_middleware.py` files to protect route groups.
5.  **Simple CLI:** Improve the CLI (e.g., `ushka new` to scaffold a project).
6.  **Dependency Injection:** *After* the core is stable, explore a simple DI system for services (like DB connections).

## Repository

GitHub: **[Your repository link here]**
