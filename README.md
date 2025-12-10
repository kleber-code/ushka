# Ushka: A Modern Asynchronous Python Web Framework

[![PyPI Version](https://img.shields.io/pypi/v/ushka)](https://pypi.org/project/ushka/)
[![Documentation](https://img.shields.io/badge/Documentation-View%20Here-blue)](https://kleber-code.github.io/ushka/)
![Python Versions](https://img.shields.io/pypi/pyversions/ushka)
![License](https://img.shields.io/pypi/l/ushka)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Ushka is a modern, asynchronous Python web framework designed for simplicity, performance, and an excellent developer experience. It provides a clean, intuitive API for building web applications and APIs with minimal boilerplate.

## Key Principles

*   **Simplicity:** Ushka's API is designed to be clean, intuitive, and easy to remember, allowing developers to focus on application logic.
*   **Performance:** Built on top of modern asynchronous libraries, Ushka is fast, efficient, and capable of handling high-concurrency applications.
*   **Developer Experience:** Features like filesystem-based routing, dependency injection, and informative error messages streamline the development workflow.
*   **Flexibility:** While offering sensible defaults, Ushka is highly extensible, allowing you to integrate with your preferred tools and libraries.

## Features

Ushka comes equipped with a rich set of features to accelerate your development:

*   **Dual Routing System:**
    *   **Filesystem-Based Routing:** Define routes simply by creating files in your `routes/` directory (e.g., `routes/users/profile.py` maps to `/users/profile`).
    *   **Decorator-Based Routing:** Explicitly define routes using Python decorators (`@app.get("/users")`).
*   **Asynchronous Core:** Built on `asyncio` for high performance and scalability, ready for concurrent operations.
*   **Active Record ORM:** A simplified, asynchronous Object-Relational Mapper based on SQLAlchemy for efficient database interactions.
*   **Jinja2 Templating:** Native support for the powerful Jinja2 templating engine, including asynchronous rendering and context processors.
*   **Comprehensive Request & Response Objects:** Easily access HTTP headers, query parameters, body data (JSON, form, raw bytes), cookies, and sessions. Flexible response handling allows returning dictionaries (auto-JSON), strings (auto-HTML), or full `Response` objects.
*   **Dependency Injection:** Automatically inject `Request`, `Response`, and configuration objects, as well as URL parameters, into your route handlers.
*   **Configurability:** Simple, automatic configuration management via `ushka.toml`, with sensible defaults.
*   **Enhanced Error Handling:** Informative and visually appealing error pages (404, 500) to aid debugging.
*   **Rich Logging:** Clear, color-coded terminal logs for better visibility into application activity.
*   **Static File Serving:** Easily serve static assets (CSS, JS, images) from a configurable directory.
*   **CLI Tools:** A command-line interface for common tasks like running the development server, managing routes, and database migrations.

## Installation

Getting started with Ushka is straightforward:

```bash
pip install ushka
```

## Quick Start

Here's a minimal example to create a simple web application using decorator-based routing:

1.  **Create your application file (e.g., `app.py`):**

    ```python
    from ushka import Ushka, Request, Response

    app = Ushka()

    @app.get("/")
    async def hello_world(request: Request) -> Response:
        return Response("<h1>Hello, Ushka!</h1>")

    @app.get("/greet/[name]")
    async def greet_name(request: Request, name: str) -> Response:
        return Response(f"Hello, {name}!")

    if __name__ == "__main__":
        app.run()
    ```

2.  **Run your application:**

    ```bash
    python app.py
    ```

3.  **Access it in your browser:**
    Open `http://127.0.0.1:8000` or `http://127.0.0.1:8000/greet/World` in your web browser.

For more detailed examples, tutorials on filesystem-based routing, and advanced usage, please refer to the [official documentation](https://kleber-code.github.io/ushka/).

## Documentation

For comprehensive guides, API reference, and tutorials, visit the [Ushka Documentation](https://kleber-code.github.io/ushka/).

## Contributing

We welcome contributions! If you find a bug, have a feature request, or want to contribute code, please check out our [Contributing Guidelines](https://github.com/kleber-code/ushka/blob/main/.github/CONTRIBUTING.md).

## License

Ushka is open-source software licensed under the [MIT License](https://github.com/kleber-code/ushka/blob/main/LICENSE).
