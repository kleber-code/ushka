"""Tools behind ``ushka i18n``: find messages, write a ``.pot``, compile ``.po`` to ``.mo``.

Standard library plus Jinja2 only (its ``babel_extract`` reads templates, no
Babel needed). The ``.po`` reader and ``.mo`` writer are deliberately small:
they handle what real catalogs contain (context, plural forms, multi-line
strings, escapes, fuzzy and obsolete entries) and nothing more.
"""

from __future__ import annotations

import ast
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

#: ``name -> positions`` of the message parts among the call arguments:
#: ``(context, singular, plural)``; ``None`` where there is none.
PY_FUNCTIONS: dict[str, tuple[int | None, int, int | None]] = {
    "_": (None, 0, None),
    "gettext": (None, 0, None),
    "lazy_gettext": (None, 0, None),
    "ngettext": (None, 0, 1),
    "pgettext": (0, 1, None),
    "npgettext": (0, 1, 2),
    "translate": (None, 1, None),
    "ntranslate": (None, 1, 2),
}
JINJA_KEYWORDS = ["_", "gettext", "ngettext", "pgettext", "npgettext"]
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "env", "site-packages", "build", "dist"}


@dataclass
class Message:
    msgid: str
    plural: str = ""
    context: str = ""
    locations: list[str] = field(default_factory=list)


# -- finding messages ---------------------------------------------------------------


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def extract_python(source: str, filename: str = "<string>") -> list[tuple[int, Message]]:
    """``(line, message)`` for every literal ``_("...")``-style call in `source`."""
    found = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name not in PY_FUNCTIONS:
            continue
        ctx_at, msg_at, plural_at = PY_FUNCTIONS[name]
        try:
            msgid = _literal(node.args[msg_at])
            context = _literal(node.args[ctx_at]) if ctx_at is not None else ""
            plural = _literal(node.args[plural_at]) if plural_at is not None else ""
        except IndexError:
            continue
        if msgid and context is not None and plural is not None:
            found.append((node.lineno, Message(msgid, plural, context)))
    return found


def extract_template(source: str) -> list[tuple[int, Message]]:
    """The same for a Jinja template: ``_()``, ``ngettext()``... and ``{% trans %}`` blocks."""
    import io

    from jinja2.ext import babel_extract

    found = []
    for lineno, function, message, _comments in babel_extract(io.BytesIO(source.encode()), JINJA_KEYWORDS, [], {}):
        parts = message if isinstance(message, tuple) else (message,)
        parts = tuple(p for p in parts if p is not None)
        if function == "pgettext" and len(parts) >= 2:
            found.append((lineno, Message(parts[1], context=parts[0])))
        elif function == "npgettext" and len(parts) >= 3:
            found.append((lineno, Message(parts[1], parts[2], context=parts[0])))
        elif function == "ngettext" and len(parts) >= 2:
            found.append((lineno, Message(parts[0], parts[1])))
        elif parts and isinstance(parts[0], str) and parts[0]:
            found.append((lineno, Message(parts[0])))
    return found


def _files(root: Path, suffixes: tuple[str, ...]):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).parts[:-1]
        if any(part.startswith(".") or part in SKIP_DIRS for part in relative):
            continue
        if path.is_file() and path.suffix in suffixes:
            yield path


def extract(root: Path, template_dirs: tuple[str, ...] = ("templates",), skip: tuple[Path, ...] = ()) -> list[Message]:
    """Every message under `root`: ``.py`` files anywhere and templates in `template_dirs`."""
    root = Path(root)
    messages: dict[tuple[str, str], Message] = {}
    skipped = tuple(Path(s).resolve() for s in skip)

    def add(path: Path, line: int, message: Message) -> None:
        entry = messages.setdefault((message.context, message.msgid), message)
        if message.plural and not entry.plural:
            entry.plural = message.plural
        location = f"{path.relative_to(root).as_posix()}:{line}"
        if location not in entry.locations:
            entry.locations.append(location)

    for path in _files(root, (".py",)):
        if any(s == path.resolve() or s in path.resolve().parents for s in skipped):
            continue
        try:
            for line, message in extract_python(path.read_text("utf-8"), str(path)):
                add(path, line, message)
        except (SyntaxError, UnicodeDecodeError):
            continue
    for name in template_dirs:
        folder = root / name
        if folder.is_dir():
            for path in _files(folder, (".html", ".htm", ".xml", ".txt", ".jinja", ".j2")):
                try:
                    for line, message in extract_template(path.read_text("utf-8")):
                        add(path, line, message)
                except Exception:  # a template with a syntax error is reported when it renders
                    continue
    return list(messages.values())


def _quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t").replace("\r", "\\r")
    return '"' + escaped.replace("\n", "\\n") + '"'


def write_pot(messages: list[Message], project: str = "PROJECT") -> str:
    """The text of a ``.pot`` template for `messages`."""
    out = [
        f"# Translations template for {project}.",
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: ' + project + '\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Language: \\n"',
        '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"',
        "",
    ]
    for m in sorted(messages, key=lambda m: (m.locations[0] if m.locations else "", m.msgid)):
        out += [f"#: {' '.join(m.locations)}"] if m.locations else []
        if m.context:
            out.append(f"msgctxt {_quote(m.context)}")
        out.append(f"msgid {_quote(m.msgid)}")
        if m.plural:
            out += [f"msgid_plural {_quote(m.plural)}", 'msgstr[0] ""', 'msgstr[1] ""']
        else:
            out.append('msgstr ""')
        out.append("")
    return "\n".join(out)


# -- .po -> .mo ----------------------------------------------------------------------

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}
_ESCAPE_RE = re.compile(r"\\(?:([ntr\"\\abfv])|([0-7]{1,3})|x([0-9a-fA-F]{1,2}))")


def _unquote(token: str, where: str) -> str:
    token = token.strip()
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        raise ValueError(f"{where}: expected a quoted string, got {token!r}")

    def replace(match: re.Match) -> str:
        if match.group(1):
            return _ESCAPES[match.group(1)]
        return chr(int(match.group(2), 8)) if match.group(2) else chr(int(match.group(3), 16))

    return _ESCAPE_RE.sub(replace, token[1:-1])


def parse_po(text: str) -> dict[str, str]:
    """``{key: value}`` ready for a ``.mo``: the entries that are translated and not fuzzy.

    A message with context has the key ``context\\x04msgid``; one with a plural,
    ``msgid\\x00plural`` and a value of the forms joined by ``\\x00``. The header
    (empty ``msgid``) is always kept, even when marked fuzzy.
    """
    entries: dict[str, str] = {}
    current: dict[str, object] = {}
    field_name = ""
    fuzzy = False

    def flush() -> None:
        nonlocal current, fuzzy
        if "msgid" in current:
            msgid = str(current["msgid"])
            forms = current.get("msgstr", {})
            values = [forms[i] for i in sorted(forms)]  # type: ignore[union-attr]
            key = msgid + ("\x00" + str(current["msgid_plural"]) if "msgid_plural" in current else "")
            if "msgctxt" in current:
                key = str(current["msgctxt"]) + "\x04" + key
            if (not fuzzy or msgid == "") and any(values):
                entries[key] = "\x00".join(values)
        current, fuzzy = {}, False

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        where = f"line {number}"
        if not line or line.startswith("#~"):
            if not line:
                flush()
                field_name = ""
            continue
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            continue
        if line.startswith('"'):
            if not field_name:
                raise ValueError(f"{where}: a string with no msgid before it")
            piece = _unquote(line, where)
            if field_name == "msgstr":
                forms = current["msgstr"]
                forms[max(forms)] += piece  # type: ignore[index]
            else:
                current[field_name] = str(current[field_name]) + piece
            continue
        keyword, _sep, rest = line.partition(" ")
        index = re.fullmatch(r"msgstr\[(\d+)\]", keyword)
        if keyword in ("msgctxt", "msgid", "msgid_plural"):
            if keyword in current or (keyword == "msgid" and "msgstr" in current) or (keyword == "msgctxt" and "msgid" in current):
                flush()
            current[keyword] = _unquote(rest, where)
            field_name = keyword
        elif keyword == "msgstr" or index:
            current.setdefault("msgstr", {})[int(index.group(1)) if index else 0] = _unquote(rest, where)  # type: ignore[index]
            field_name = "msgstr"
        else:
            raise ValueError(f"{where}: unexpected {keyword!r}")
    flush()
    return entries


def write_mo(entries: dict[str, str]) -> bytes:
    """A GNU ``.mo`` file for `entries` (sorted by key, as the format requires)."""
    keys = sorted(entries, key=lambda k: k.encode("utf-8"))
    ids = [k.encode("utf-8") for k in keys]
    strs = [entries[k].encode("utf-8") for k in keys]
    count = len(keys)
    key_offsets, value_offsets, blob = [], [], b""
    base = 28 + 16 * count  # the strings follow the header and both tables
    for item in ids:
        key_offsets.append((len(item), base + len(blob)))
        blob += item + b"\0"
    for item in strs:
        value_offsets.append((len(item), base + len(blob)))
        blob += item + b"\0"
    header = struct.pack("<7I", 0x950412DE, 0, count, 28, 28 + 8 * count, 0, 0)
    table = b"".join(struct.pack("<2I", *pair) for pair in key_offsets + value_offsets)
    # the two tables are laid out one after the other: originals, then translations
    return header + table + blob


def compile_po(po_path: Path, mo_path: Path | None = None) -> Path:
    """Compiles `po_path` (UTF-8) into a ``.mo`` next to it; raises `ValueError` naming the file and line on bad input."""
    po_path = Path(po_path)
    mo_path = Path(mo_path) if mo_path else po_path.with_suffix(".mo")
    try:
        entries = parse_po(po_path.read_text("utf-8"))
    except ValueError as exc:
        raise ValueError(f"{po_path}: {exc}") from exc
    mo_path.write_bytes(write_mo(entries))
    return mo_path
