# Roadmap

Ushka is currently in **Alpha**, but we have big dreams and a clear vision for the future. Our goal is to create the most developer-friendly micro-framework available, without sacrificing performance or power.

This roadmap is a living document and may change based on community feedback.

---

## Core Features (Already Implemented)

Ushka already comes with a powerful set of features designed for rapid development and a great developer experience.

-   **Dual Routing System**:
    -   **Auto-Discovery**: Automatic route mapping based on the `routes/` folder.
    -   **Decorator-Based**: Explicitly define routes with `@app.get()`, `@app.post()`, etc. (Flask-like style).
-   **Smart Response**: Automatic conversion of `dict` to JSON and `str` to HTML.
-   **Request Handling**: Easy access to request data (`json`, `form`, `query`, `headers`) via the `Request` object.
-   **Dynamic Routes**: Support for parameters in file names (`[id].py`) and decorator paths (`/users/{id}`).
-   **Jinja2 Templates**: Native support for rendering Jinja2 templates.
-   **Zero-Config & Auto-Config**: Automatic generation and reading of `ushka.toml` on first run.
-   **Advanced Error Handling**:
    -   **Debug Mode ("Ushka Panic")**: A beautiful, interactive debug page with a full stack trace and local variables.
    -   **Production Mode**: A clean, stylized "Not Found" page and generic public error pages.
-   **Basic Dependency Injection**: Automatic injection of `Request` object and URL parameters into route functions.
-   **ASGI Core**: Fully asynchronous, based on Uvicorn, including support for `lifespan` events.
-   **Comprehensive Documentation**: A detailed documentation website (which you are reading right now!).

---

## Short-Term Goals (The Path to v0.5)

Our immediate focus is on solidifying the foundational features required for most web applications.

-   [ ] **Static File Support**: Provide a simple and efficient way to serve static files like CSS, JavaScript, and images.
-   [ ] **Multipart Body Request**: Efficiently handle large file uploads with streaming support.
-   [ ] **Ushka CLI - `new` command**: A command-line tool to scaffold projects with different templates (`minimal`, `full`, `packet`).
-   [ ] **Advanced Dependency Injection**: Automatically inject and validate data from `json`, `query`, and `form` directly into function arguments.

## Maturing Mid-Term Goals (The Road to v1.0)

As the framework matures, we will focus on features that enable larger and more complex applications.

-   [ ] **Middleware System**: A robust and simple system to intercept and process requests and responses.
-   [ ] **Cookies & Sessions**: Native support for managing client-side state.
-   [ ] **Sub-apps (Blueprints)**: A way to organize larger applications by splitting them into smaller, reusable "apps" or "routers."
-   [ ] **Embedded Authentication**: An optional, built-in login system (`ushka.auth`).

## Long-Term & Vision (Beyond v1.0)

These are the ambitious, "game-changer" features that will define the future of Ushka.

-   [ ] **Native Documentation System**: An automatic, interactive API documentation and playground, generated from your code (similar to FastAPI's docs).
-   [ ] **Ushka CLI - `deploy` command**: A powerful deployment tool with auto-configuration for Nginx, Systemd, and workers.
-   [ ] **A Stable and Reliable API**: Reaching v1.0 means a commitment to a stable public API with a clear deprecation policy.
-   [ ] **Performance Parity**: Continuous performance tuning to ensure Ushka is competitive with other top-tier ASGI frameworks.
-   [ ] **WebSockets Support**: Native support for handling WebSocket connections.
-   [ ] **ORM Integration**: Official guides and potential plugins for popular ORMs.

We are excited about the future of Ushka and welcome contributions and feedback from the community to help us achieve these goals.
