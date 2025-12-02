# 🗺️ Ushka Roadmap

> **Status:** 🟢 Alpha  
> **Goal:** High-performance, developer-friendly micro-framework.

**Ushka** is currently in **Alpha**, brimming with ambitious plans! Our ultimate goal is to craft the most developer-friendly micro-framework out there, without making you sacrifice performance.

This roadmap is a living document. Feedback is welcome! 💌

---

## 💎 Current Capabilities (Implemented)

Ushka already packs a serious punch with features designed for rapid development.

- [x] **Dual Routing System**
    - **Auto-Discovery:** File-based routing in `routes/`.
    - **Decorator-Based:** Explicit routing (e.g., `@app.route`).
- [x] **Smart Response Handling**
    - Auto-conversion of `dict` to JSON and `str` to HTML.
- [x] **Lazy Request Object**
    - On-demand access to `json`, `form`, `query`, and `headers`.
- [x] **Dynamic Routing**
    - Supports `[id].py` and `/users/{id}` patterns.
- [x] **Jinja2 Template Support**
    - Native rendering support out of the box.
- [x] **Zero-Config Setup**
    - Auto-generation of `ushka.toml`.
- [x] **Advanced Error Handling**
    - **Debug Mode:** Interactive "Ushka Panic!" page with stack trace.
    - **Production Mode:** Clean, stylized error pages.
- [x] **Dependency Injection**
    - Injection of `Request` object and URL parameters.
- [x] **ASGI Core**
    - Fully asynchronous, built on top of Uvicorn.

---

## 🚧 Development Roadmap

### 📍 v0.5: The Sprint (Short-Term)
*Focus: Strengthening the foundation and developer tools.*

- [x] **Static File Serving**
    - Zero-config serving from `static/` directory.
- [ ] **Multipart Body Request**
    - Handle file uploads with streaming support.
- [ ] **Ushka CLI: `new` command**
    - Project scaffolding wizard (`minimal`, `full`, `packet`).
- [ ] **Advanced Dependency Injection**
    - Auto-inject and validate data from `json`, `query`, and `form` directly into function args.

### 🎀 v1.0: Maturity (Mid-Term)
*Focus: Robustness and complex application support.*

- [ ] **Middleware System**
    - Flexible interception of requests/responses.
- [ ] **Cookies & Sessions**
    - Native support for client-side state management.
- [ ] **Sub-apps (Blueprints)**
    - Organizing larger apps into reusable routers.
- [ ] **Embedded Authentication**
    - Built-in, optional login system (`ushka.auth`).

### 🚀 Beyond v1.0: The Vision (Long-Term)
*Focus: Ecosystem, stability, and enterprise features.*

- [ ] **Native Documentation System**
    - Auto-generated interactive API docs (Swagger/OpenAPI style).
- [ ] **Ushka CLI: `deploy` command**
    - Tools for Nginx, Systemd, and worker configuration.
- [ ] **Stable Public API**
    - Strict versioning and deprecation policies.
- [ ] **Performance Parity**
    - Continuous tuning for competitive benchmarks.
- [ ] **WebSockets Support**
    - Native support for real-time connections.
- [ ] **ORM Integration**
    - Official guides/plugins for popular ORMs.

---

## 🤝 Contributing

We thrive on community contributions! If you have ideas or want to help us check off some of these boxes, please check our contribution guidelines.