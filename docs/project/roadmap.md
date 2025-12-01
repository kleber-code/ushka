# 🗺️ Ushka's Roadmap: Big Dreams for a Little Framework! 🚀

(Or: Our Grand Plan to Conquer the Web, One Cute Feature at a Time.)

Ushka is currently in **Alpha** (think of us as a spirited toddler with a powerful brain), but we're brimming with ambitious plans! Our ultimate goal? To craft the most developer-friendly micro-framework out there, without making you sacrifice performance or, you know, your sanity. 💪

Consider this roadmap our public wishlist. It's a living document, so it might shift a bit based on what our fantastic community (that's you!) tells us. Don't be shy! We love feedback, even the constructive kind. 💌

---

## 🌟 Core Features: What Ushka Already Aces! (No, really!)

Before we talk about where we're going, let's appreciate how far we've come! Ushka already packs a serious punch with features designed for rapid development and a developer experience so smooth, it's almost suspicious. We wouldn't want to brag, but...

*   💖 **Dual Routing System: Pick Your Poison (or Perfection)!**
    *   **Auto-Discovery:** Just drop a file in `routes/`, and *poof*! Your route exists. It's like magic, but for backend.
    *   **Decorator-Based:** Prefer being explicit? Define your routes with decorators, just like those other popular frameworks. We won't judge.
*   💖 **Smart Response: Less Code, More Zen!**
    Ushka intelligently converts `dict` to JSON and `str` to HTML. Because who has time for boilerplate?
*   💖 **Request Handling: All Your Data, On Demand!**
    Easily grab all request data (`json`, `form`, `query`, `headers`) via the `Request` object. We made it lazy so your app stays fast.
*   💖 **Dynamic Routes: Paths That Adapt!**
    Supports parameters in file names (`[id].py`) and decorator paths (`/users/{id}`). Because your URLs deserve to be flexible.
*   💖 **Jinja2 Templates: Pretty Pages, Simple Syntax!**
    Native support for rendering Jinja2 templates. Make your frontend look good without shedding tears.
*   💖 **Zero-Config & Auto-Config: It Just Works™!**
    Ushka generates and reads your `ushka.toml` on first run. Setup? What setup?
*   💖 **Advanced Error Handling: Mistakes Happen, Elegantly!**
    *   **Debug Mode ("Ushka Panic!"):** A beautiful, interactive debug page with a full stack trace and local variables. Debugging doesn't have to be dreadful.
    *   **Production Mode:** Clean, stylized "Not Found" and generic error pages. Because security and aesthetics can coexist.
*   💖 **Basic Dependency Injection: Smart, Not Spooky!**
    Automatically injects the `Request` object and URL parameters into your route functions. Your functions, smarter.
*   💖 **ASGI Core: Fast & Furious (but in a good way)!**
    Fully asynchronous, built on Uvicorn. Your app will fly.
*   💖 **Comprehensive Documentation: (You're reading it, aren't you?)**
    A detailed documentation website. We try our best to explain things without making you fall asleep.

---

## 🌠 Short-Term Goals (The Sprint to v0.5): What's Next on the To-Do List?

Alright, enough basking in past glories! Here's what's immediately on our plate. Our immediate focus is beefing up Ushka's foundational features to make your life even easier.

*   [ ] **Static File Support:** A simple, efficient way to serve static assets. Because even minimalist apps need pretty pictures.
*   [ ] **Multipart Body Request:** Handle those bulky file uploads with streaming support. Because everyone deserves proper file handling.
*   [ ] **Ushka CLI - `new` command:** A command-line wizard to scaffold projects (`minimal`, `full`, `packet`). For when you want to start coding, like, five minutes ago.
*   [ ] **Advanced Dependency Injection:** Automatically inject and validate data from `json`, `query`, and `form` directly into function arguments. Less manual parsing, more doing.

## 🎀 Mid-Term Dreams (The Climb to v1.0): Getting Serious (but still cute)!

As Ushka matures, we'll shift our focus to features that enable more robust and complex applications. We're growing up so fast!

*   [ ] **Middleware System:** A flexible system to intercept and process requests/responses. Because sometimes you need to meddle a little.
*   [ ] **Cookies & Sessions:** Native support for managing client-side state. So your users can feel remembered.
*   [ ] **Sub-apps (Blueprints):** Organize larger applications into smaller, reusable "apps" or "routers." For when your project gets too big for one file.
*   [ ] **Embedded Authentication:** An optional, built-in login system (`ushka.auth`). Because security shouldn't be a puzzle.

## 🌈 Long-Term Vision (Beyond v1.0): The Sky's the Limit (Almost)!

These are the big, audacious, "we're gonna change the game" features. The kind that makes you go, "Whoa, Ushka can do *that*?"

*   [ ] **Native Documentation System:** Automatic, interactive API docs generated from your code (think FastAPI, but with more personality).
*   [ ] **Ushka CLI - `deploy` command:** A powerful deployment tool with auto-configuration for Nginx, Systemd, and workers. Deploying should be less painful.
*   [ ] **A Stable and Reliable API:** Reaching v1.0 means a rock-solid public API with a clear deprecation policy. We take stability seriously. (Mostly.)
*   [ ] **Performance Parity:** Continuous performance tuning to ensure Ushka is competitive. Fast is good. Slow is... well, you know.
*   [ ] **WebSockets Support:** Native support for WebSocket connections. Real-time apps, here we come!
*   [ ] **ORM Integration:** Official guides and potential plugins for popular ORMs. Because databases are important, even if they're not always cute.

We're genuinely excited about Ushka's future and we absolutely thrive on community contributions and feedback. Help us build something truly special! (And maybe send us some coffee.) 💖