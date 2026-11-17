"""``ushka verify``: attack your own app and report what got through.

It sends hostile payloads (XSS, SQL injection, template injection, path
traversal, open redirect, header injection, junk input) to every route, in the
process, with no network, and checks what comes back. It can only reach the
app object you give it, never another server.

Every probe ends in one of these:

* **blocked**: refused by validation (422), the guard, or an HTTP error;
* **guard**: the guard refused it inside your handler (the request would be a 500
  for a real visitor, so sanitise there: the report shows the line to write);
* **handled**: the request went through and the payload did no harm;
* **VULNERABLE**: the payload did its job (reflected as markup, injected a header...);
* **crash**: the handler raised on hostile input.

Only ``GET`` routes are probed by default, because probing runs your real
handlers. ``include_writes`` also probes ``POST``/``PUT``/``PATCH``/``DELETE``:
point it at a test database.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import datetime as dt
import enum
import inspect
import json
import logging
import re
import textwrap
import typing
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, unquote, urlencode, urlsplit

from ushka.api.openapi import _PATH_SEGMENT
from ushka.guard import RejectedValueError, UnsafeValueError
from ushka.http.exceptions import HTTPError
from ushka.http.params import build_plan
from ushka.http.validation import RequestValidationError, hints_of

SAFE = {"GET", "HEAD"}
SEVERITY = {"high": 3, "medium": 2, "low": 1}
_SQL_ERRORS = re.compile(
    r"syntax error|unrecognized token|unterminated quoted|SQLSTATE|sqlite3?\.\w*Error|"
    r"OperationalError|ProgrammingError|near \"'\"|you have an error in your sql|ORA-\d{5}|psycopg",
    re.IGNORECASE,
)
_MARKUP = ("text/html", "application/xhtml+xml", "image/svg+xml", "text/xml")


@dataclasses.dataclass(frozen=True)
class Payload:
    category: str
    value: str
    risk: str


PAYLOADS = (
    Payload("xss", "<script>alert(1337)</script>", "cross-site scripting"),
    Payload("xss", '"><img src=x onerror=alert(1337)>', "cross-site scripting"),
    Payload("sqli", "' OR '1'='1' --", "SQL injection"),
    Payload("sqli", "1'", "SQL injection"),
    Payload("ssti", "{{1337*3}}${1337*3}", "template injection"),
    Payload("traversal", "../../../../../../etc/passwd", "path traversal"),
    Payload("redirect", "//evil.example/x", "open redirect"),
    Payload("crlf", "x\r\nX-Injected: 1337", "header injection"),
    Payload("junk", "\x00" + "A" * 20000, "unhandled hostile input"),
)


@dataclasses.dataclass
class Finding:
    severity: str  # high | medium | low
    kind: str  # VULNERABLE | crash | guard | config
    category: str
    route: str
    slot: str
    detail: str
    fix: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Report:
    probes: int = 0
    outcomes: dict[str, int] = dataclasses.field(default_factory=lambda: {"blocked": 0, "guard": 0, "handled": 0, "vulnerable": 0, "crash": 0})
    findings: list[Finding] = dataclasses.field(default_factory=list)
    routes: int = 0
    skipped: list[str] = dataclasses.field(default_factory=list)

    def add(self, finding: Finding) -> None:
        """Adds a finding unless the same problem on the same input is already there."""
        key = (finding.kind, finding.category, finding.route, finding.slot)
        if not any((f.kind, f.category, f.route, f.slot) == key for f in self.findings):
            self.findings.append(finding)

    def failing(self, fail_on: str = "medium") -> list[Finding]:
        if fail_on == "none":
            return []
        floor = SEVERITY[fail_on]
        return [f for f in self.findings if SEVERITY[f.severity] >= floor]

    def to_dict(self) -> dict:
        return {"routes": self.routes, "probes": self.probes, "outcomes": self.outcomes, "skipped": self.skipped, "findings": [f.to_dict() for f in self.findings]}


# -- discovering what a route reads ---------------------------------------------------


def _baseline(tp: Any, depth: int = 0) -> Any:
    """A valid value for type `tp`, so a probe changes only the one field under test."""
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Annotated:
        return _baseline(args[0], depth)
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        return _baseline(next((a for a in args if a is not type(None)), str), depth)
    if origin is typing.Literal:
        return args[0]
    if origin in (list, set, frozenset, tuple):
        return [_baseline(args[0], depth)] if args and args[0] is not Ellipsis else []
    if origin is dict or tp is dict:
        return {}
    if isinstance(tp, type):
        if issubclass(tp, enum.Enum):
            return next(iter(tp)).value
        if tp is bool:
            return True
        if tp is int:
            return 1
        if tp is float:
            return 1.5
        if tp is uuid.UUID:
            return str(uuid.uuid4())
        if tp is dt.datetime:
            return "2024-01-01T00:00:00"
        if tp is dt.date:
            return "2024-01-01"
        if tp is dt.time:
            return "12:00:00"
        if dataclasses.is_dataclass(tp) and depth < 3:
            hints = hints_of(tp)
            return {f.name: _baseline(hints.get(f.name, str), depth + 1) for f in dataclasses.fields(tp) if f.init and f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
        if typing.is_typeddict(tp) and depth < 3:
            return {k: _baseline(v, depth + 1) for k, v in hints_of(tp).items()}
    return "test"


def _query_names_in_source(func: Callable) -> set[str]:
    """Names a handler reads with ``request.query.get("q")`` or ``request.query["q"]``."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    except (OSError, TypeError, SyntaxError):
        return set()

    def is_query(node: ast.AST) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == "query"

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and is_query(node.func.value) and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value)
        elif isinstance(node, ast.Subscript) and is_query(node.value) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            names.add(node.slice.value)
    return names


@dataclasses.dataclass
class Slot:
    where: str  # path | query | body
    name: str
    baseline: Any = "test"


def discover_slots(method: str, raw_path: str, func: Callable, extra_params=()) -> list[Slot]:
    names = frozenset(_PATH_SEGMENT.findall(raw_path))
    slots: dict[tuple[str, str], Slot] = {}
    for n in names:
        slots[("path", n)] = Slot("path", n, "1")
    for spec in build_plan(func, names, method):
        marker = spec.marker
        name = marker.alias if marker and marker.alias else spec.name
        if spec.kind == "path" and spec.name in names:
            slots[("path", spec.name)] = Slot("path", spec.name, str(_baseline(spec.annotation)))
        elif spec.kind == "query":
            slots[("query", name)] = Slot("query", name, _baseline(spec.annotation))
        elif spec.kind == "body":
            slots[("body", name)] = Slot("body", name, _baseline(spec.annotation))
    for name in _query_names_in_source(func) | set(extra_params):
        slots.setdefault(("query", name), Slot("query", name, "test"))
    return list(slots.values())


# -- running probes ---------------------------------------------------------------------


class _Client:
    def __init__(self, app, host: str) -> None:
        self.app, self.host = app, host
        self.last_exc: BaseException | None = None
        original = app.error_handler.handle_exception

        async def recording(exc, request):
            self.last_exc = exc
            return await original(exc, request)

        self._original = original
        app.error_handler.handle_exception = recording

    def close(self) -> None:
        self.app.error_handler.handle_exception = self._original

    async def send(self, method: str, path: str, query: dict | None = None, body: Any = None, headers: dict | None = None, raw_body: bytes | None = None) -> dict:
        self.last_exc = None
        payload = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else b"")
        hdrs = {"host": self.host, **(headers or {})}
        if body is not None or raw_body is not None:
            hdrs.setdefault("content-type", "application/json")
        hdrs["content-length"] = str(len(payload))
        pairs = [(k, str(i)) for k, v in (query or {}).items() for i in (v if isinstance(v, list) else [v])]
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
            "path": unquote(path), "raw_path": path.encode("latin-1", "replace"), "query_string": urlencode(pairs, errors="replace").encode(errors="replace"),
            "root_path": "", "headers": [(k.lower().encode("latin-1"), v.encode("utf-8", "replace")) for k, v in hdrs.items()],
            "client": ("127.0.0.1", 9), "server": (self.host, 80),
        }
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            sent.append(message)

        raised: BaseException | None = None
        try:
            await asyncio.wait_for(self.app(scope, receive, send), 15)
        except asyncio.TimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001 - an app that raises out of ASGI is a finding, not a harness error
            raised = exc
        start = next((m for m in sent if m["type"] == "http.response.start"), {"status": 500, "headers": []})
        headers_out = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in start["headers"]}
        raw = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return {"status": start["status"], "headers": headers_out, "body": raw.decode("utf-8", "replace"), "exc": raised or self.last_exc}


def _inspect(payload: Payload, res: dict) -> str | None:
    """Evidence that `payload` worked, or None."""
    body, headers = res["body"], res["headers"]
    ctype = headers.get("content-type", "").split(";")[0].strip().lower()
    marker = payload.value[:40]
    if payload.category == "xss" and ctype in _MARKUP and payload.value in body:
        return "the payload came back as live markup in an HTML response"
    if payload.category == "ssti" and "4011" in body and marker not in body:
        return "the template expression was evaluated (1337*3 became 4011)"
    if payload.category == "traversal" and re.search(r"root:.*:0:0:", body):
        return "the response contains the contents of /etc/passwd"
    if payload.category == "redirect" and 300 <= res["status"] < 400:
        host = urlsplit(headers.get("location", "")).netloc
        if host == "evil.example":
            return f"redirected to an attacker-chosen site (Location: {headers['location']})"
    if payload.category == "crlf" and "x-injected" in headers:
        return "an injected header appeared in the response"
    if payload.category == "sqli" and _SQL_ERRORS.search(body):
        return "the response leaks a database error, so the input reached the SQL"
    return None


def _build(method: str, raw_path: str, slots: list[Slot], target: Slot | None, value: Any):
    path = raw_path
    query: dict[str, Any] = {}
    body: dict[str, Any] = {}
    for s in slots:
        v = value if s is target else s.baseline
        if s.where == "path":
            path = re.sub(r"\[(?:(?:path|int):)?" + re.escape(s.name) + r"\]", lambda _m, v=v: quote(str(v), safe="/" if "[path:" in raw_path else ""), path)
        elif s.where == "query":
            query[s.name] = v
        else:
            body[s.name] = v
    sole_body = [s for s in slots if s.where == "body"]
    json_body: Any = None
    if sole_body:
        json_body = body[sole_body[0].name] if len(sole_body) == 1 else body
    return path, query, json_body


async def _classify(report: Report, res: dict, route: str, slot: Slot, payload: Payload) -> None:
    exc = res["exc"]
    report.probes += 1
    if isinstance(exc, UnsafeValueError):
        report.outcomes["guard"] += 1
        report.add(Finding("low", "guard", payload.category, route, f"{slot.where}:{slot.name}",
            f"[{exc.code}] untrusted {slot.where} value reached {exc.sink} ({exc.risk}); a real visitor would get a 500", exc.fix))
    elif isinstance(exc, (RejectedValueError, RequestValidationError, HTTPError)) or (exc is None and 400 <= res["status"] < 500):
        report.outcomes["blocked"] += 1
    elif exc is not None and not (isinstance(exc, ValueError) and "header" in str(exc).lower()):
        report.outcomes["crash"] += 1
        report.add(Finding("medium", "crash", payload.category, route, f"{slot.where}:{slot.name}",
            f"{type(exc).__name__} on hostile input ({payload.risk} probe): {str(exc)[:120]}", "Validate the input with a typed parameter or a ushka.guard.safe sanitiser."))
    elif exc is not None:
        report.outcomes["blocked"] += 1  # the framework refused to build a response with a forged header
    elif (evidence := _inspect(payload, res)) is not None:
        report.outcomes["vulnerable"] += 1
        report.add(Finding("high", "VULNERABLE", payload.category, route, f"{slot.where}:{slot.name}", f"{payload.risk}: {evidence}",
            "Pass the value through ushka.guard.safe, or turn Ushka Guard back on ([security] taint = true)."))
    else:
        report.outcomes["handled"] += 1


class _Lifespan:
    """Runs the app's startup and shutdown hooks around the probes, as a server would."""

    def __init__(self, app) -> None:
        self.app = app
        self.queue: asyncio.Queue = asyncio.Queue()
        self.events = {"startup": asyncio.Event(), "shutdown": asyncio.Event()}
        self.error: str | None = None
        self.task: asyncio.Future | None = None

    async def _receive(self):
        return await self.queue.get()

    async def _send(self, message) -> None:
        kind = message["type"]
        if kind.endswith(".failed"):
            self.error = message.get("message", "lifespan failed")
            for event in self.events.values():
                event.set()
        elif kind == "lifespan.startup.complete":
            self.events["startup"].set()
        elif kind == "lifespan.shutdown.complete":
            self.events["shutdown"].set()

    async def start(self) -> None:
        self.task = asyncio.ensure_future(self.app({"type": "lifespan"}, self._receive, self._send))
        await self.queue.put({"type": "lifespan.startup"})
        await asyncio.wait_for(self.events["startup"].wait(), 30)
        if self.error:
            raise RuntimeError(f"startup hook failed: {self.error}")

    async def stop(self) -> None:
        if self.task is None:
            return
        await self.queue.put({"type": "lifespan.shutdown"})
        try:
            await asyncio.wait_for(self.events["shutdown"].wait(), 30)
        finally:
            self.task.cancel()


async def run(app, include_writes: bool = False, extra_params=(), max_probes_per_route: int = 200) -> Report:
    report = Report()
    config = app.config
    if config.get("app_debug"):
        report.add(Finding("high", "config", "debug", "-", "-", "debug is on: error pages show tracebacks and local variables", "Set USHKA_APP_DEBUG=false in production."))
    if config.get("security_taint") is False:
        report.add(Finding("high", "config", "guard", "-", "-", "Ushka Guard is disabled ([security] taint = false)", "Remove that setting."))
    if not app.security.headers:
        report.add(Finding("medium", "config", "headers", "-", "-", "security headers are turned off ([security] headers = false)", "Remove that setting, or set a CSP of your own."))

    hosts = [h for h in app.security.allowed_hosts if "*" not in h]
    client = _Client(app, hosts[0] if hosts else "localhost")
    skip = getattr(app, "_openapi_skip", set())
    mcp_path = getattr(getattr(app, "mcp", None), "path", None)
    lifespan = _Lifespan(app)
    log = logging.getLogger("ushka")
    previous_level, log.level = log.level, logging.CRITICAL + 1  # every hostile probe would log a traceback
    try:
        await lifespan.start()
        routes = [(m, p, f) for m, p, f in app.router.iter_routes() if m != "WEBSOCKET" and f not in skip and p != mcp_path]
        report.routes = len(routes)
        for method, raw_path, func in sorted(routes, key=lambda r: (r[1], r[0])):
            label = f"{method} {raw_path}"
            unsafe = method not in SAFE
            if unsafe:
                await _cross_site_probe(report, client, app, method, raw_path, func, label, include_writes)
                if not include_writes:
                    report.skipped.append(f"{label} (writes data: use --include-writes against a test database)")
                    continue
            slots = discover_slots(method, raw_path, func, extra_params)
            if not slots:
                continue
            sent = 0
            for slot in slots:
                for payload in PAYLOADS:
                    if sent >= max_probes_per_route:
                        break
                    sent += 1
                    path, query, body = _build(method, raw_path, slots, slot, payload.value)
                    try:
                        res = await client.send(method, path, query, body)
                    except asyncio.TimeoutError:
                        report.probes += 1
                        report.outcomes["crash"] += 1
                        report.add(Finding("medium", "crash", payload.category, label, f"{slot.where}:{slot.name}", "no answer within 15 s (possible hang or denial of service)", ""))
                        continue
                    await _classify(report, res, label, slot, payload)
        await _headers_probe(report, client, routes)
    finally:
        client.close()
        log.level = previous_level
        try:
            await lifespan.stop()
        except Exception as exc:  # noqa: BLE001 - a failing shutdown hook is reported, not allowed to hide the rest
            report.skipped.append(f"shutdown hook failed: {type(exc).__name__}: {str(exc)[:100]}")
    return report


async def _cross_site_probe(report: Report, client: _Client, app, method: str, raw_path: str, func, label: str, include_writes: bool) -> None:
    """A cross-site browser write must be refused before the handler runs."""
    sec = app.security
    if not sec.csrf:
        report.add(Finding("high", "config", "csrf", label, "-", "CSRF protection is off ([security] csrf = false), so any website can make a visitor's browser call this route", "Remove that setting, or list trusted origins in csrf_trusted_origins."))
        return
    if any(raw_path == p or raw_path.startswith(p.rstrip("/") + "/") for p in sec.csrf_exempt):
        report.skipped.append(f"{label} (exempt from CSRF by csrf_exempt_paths: not probed)")
        return
    slots = discover_slots(method, raw_path, func)
    path, query, body = _build(method, raw_path, slots, None, None)
    res = await client.send(method, path, query, body, {"sec-fetch-site": "cross-site", "origin": "https://evil.example"})
    report.probes += 1
    if res["status"] == 403:
        report.outcomes["blocked"] += 1
    else:
        report.outcomes["vulnerable"] += 1
        report.add(Finding("high", "VULNERABLE", "csrf", label, "-", f"a cross-site {method} was accepted (HTTP {res['status']})", "Check that nothing bypasses the security middleware."))


async def _headers_probe(report: Report, client: _Client, routes) -> None:
    gets = [p for m, p, _ in routes if m == "GET" and "[" not in p]
    res = await client.send("GET", gets[0] if gets else "/")
    missing = [h for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy") if h not in res["headers"]]
    if missing and not any(f.category == "headers" for f in report.findings):
        report.add(Finding("medium", "config", "headers", "GET " + (gets[0] if gets else "/"), "-", "missing security headers: " + ", ".join(missing), "Do not disable [security] headers, or set them on the route."))
