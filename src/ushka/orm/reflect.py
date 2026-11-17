"""Reads an existing database and writes Ushka models for it.

``ushka db inspect`` uses this to adopt a schema that another ORM (Django,
SQLAlchemy, Prisma...) created. Reflection goes through SQLAlchemy's generic
inspector, so it works with every backend SQLAlchemy supports.

What the database *cannot* say matters as much as what it does: defaults,
``auto_now`` and ``ON DELETE`` are often applied in Python by the old ORM and
never reach the schema. Every such gap is reported as a `Finding` and written
into the generated code as a ``TODO(ushka db inspect)`` comment. Guesses are
only ever suggestions: they are never applied silently.
"""

from __future__ import annotations

import contextlib
import keyword
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
import sqlalchemy.types as sqltypes
from sqlalchemy.ext.asyncio import create_async_engine

#: tables that belong to tools, not to the application
SYSTEM_TABLES = frozenset({"alembic_version"})

#: attribute names a model cannot use for a column (SQLAlchemy and `db.Model` own them)
RESERVED_ATTRS = frozenset(
    {"metadata", "registry", "query", "save", "delete", "to_dict", "create", "all",
     "get", "first", "filter", "select"}
)

_CREATED = frozenset(
    {"created_at", "created", "created_on", "criado_em", "criado_at", "data_criacao",
     "dt_criacao", "date_created", "creation_date"}
)
_UPDATED = frozenset(
    {"updated_at", "updated", "updated_on", "modified_at", "modified", "modified_on",
     "atualizado_em", "data_atualizacao", "dt_atualizacao", "date_updated",
     "date_modified"}
)


# =============================================================================
# What the database says
# =============================================================================


@dataclass
class ColumnInfo:
    name: str
    type: Any
    nullable: bool = True
    default: str | None = None  # the server default, as SQL text
    autoincrement: bool = False


@dataclass
class ForeignKeyInfo:
    columns: list[str]
    ref_schema: str | None
    ref_table: str
    ref_columns: list[str]
    ondelete: str | None = None  # None means NO ACTION
    onupdate: str | None = None


@dataclass
class IndexInfo:
    name: str | None
    columns: list[str]
    unique: bool = False


@dataclass
class TableInfo:
    name: str
    schema: str | None = None
    columns: list[ColumnInfo] = field(default_factory=list)
    pk: list[str] = field(default_factory=list)
    fks: list[ForeignKeyInfo] = field(default_factory=list)
    indexes: list[IndexInfo] = field(default_factory=list)
    uniques: list[IndexInfo] = field(default_factory=list)


@dataclass
class Finding:
    """Something the database does not say, or a guess that needs a human."""

    kind: str
    table: str
    column: str | None
    message: str
    suggestion: str = ""

    def where(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table


def _action(value: str | None) -> str | None:
    """Normalises a referential action; ``NO ACTION`` is the same as no clause."""
    value = (value or "").strip().upper()
    return None if value in ("", "NO ACTION") else value


def _reflect_sync(conn, schema: str | None, only: list[str] | None) -> list[TableInfo]:
    insp = sa.inspect(conn)
    available = sorted(insp.get_table_names(schema=schema))
    if only:
        missing = [t for t in only if t not in available]
        if missing:
            raise LookupError(
                f"no such table: {', '.join(missing)} "
                f"(the database has: {', '.join(available) or 'no tables'})"
            )
        names = list(only)
    else:
        names = [t for t in available if t not in SYSTEM_TABLES]

    tables = []
    for name in names:
        info = TableInfo(name=name, schema=schema)
        for c in insp.get_columns(name, schema=schema):
            default = c.get("default")
            info.columns.append(
                ColumnInfo(
                    name=c["name"],
                    type=c["type"],
                    nullable=bool(c.get("nullable", True)),
                    default=None if default is None else str(default),
                    autoincrement=bool(c.get("autoincrement")) or bool(c.get("identity")),
                )
            )
        info.pk = list(insp.get_pk_constraint(name, schema=schema).get("constrained_columns") or [])
        for fk in insp.get_foreign_keys(name, schema=schema):
            options = fk.get("options") or {}
            info.fks.append(
                ForeignKeyInfo(
                    columns=list(fk["constrained_columns"]),
                    ref_schema=fk.get("referred_schema"),
                    ref_table=fk["referred_table"],
                    ref_columns=list(fk["referred_columns"]),
                    ondelete=_action(options.get("ondelete")),
                    onupdate=_action(options.get("onupdate")),
                )
            )
        for ix in insp.get_indexes(name, schema=schema):
            if str(ix.get("name") or "").startswith("sqlite_autoindex"):
                continue
            info.indexes.append(
                IndexInfo(ix.get("name"), list(ix["column_names"]), bool(ix.get("unique")))
            )
        for uq in insp.get_unique_constraints(name, schema=schema):
            info.uniques.append(IndexInfo(uq.get("name"), list(uq["column_names"]), True))
        tables.append(info)
    return tables


async def reflect(url: str, schema: str | None = None, only: list[str] | None = None) -> list[TableInfo]:
    """Reflects the tables of the database at `url` (an async URL).

    Raises `LookupError` when a requested table does not exist.
    """
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_reflect_sync, schema, only)
    finally:
        await engine.dispose()


def table_from_model(table: sa.Table) -> TableInfo:
    """Describes a mapped `Table` the way `reflect` describes a database table."""
    info = TableInfo(name=table.name, schema=table.schema)
    for c in table.columns:
        info.columns.append(
            ColumnInfo(
                name=c.name,
                type=c.type,
                nullable=bool(c.nullable),
                default=None if c.server_default is None else "<server default>",
                autoincrement=bool(c.autoincrement is True or (c.primary_key and c.autoincrement == "auto")),
            )
        )
    info.pk = [c.name for c in table.primary_key.columns]
    for fk in table.foreign_key_constraints:
        elems = list(fk.elements)
        info.fks.append(
            ForeignKeyInfo(
                columns=[e.parent.name for e in elems],
                ref_schema=elems[0].column.table.schema,
                ref_table=elems[0].column.table.name,
                ref_columns=[e.column.name for e in elems],
                ondelete=_action(fk.ondelete),
                onupdate=_action(fk.onupdate),
            )
        )
    return info


# =============================================================================
# Types
# =============================================================================


def kind_of(t: Any) -> str:
    """The family of a SQLAlchemy type: what the Ushka helper for it would be."""
    if isinstance(t, sqltypes.Boolean):
        return "bool"
    if isinstance(t, sqltypes.Enum):
        return "enum"
    if isinstance(t, sqltypes.Uuid):
        return "uuid"
    if isinstance(t, sqltypes.JSON):
        return "json"
    if isinstance(t, sqltypes._Binary):
        return "binary"
    if isinstance(t, sqltypes.DateTime):
        return "datetime"
    if isinstance(t, sqltypes.Date):
        return "date"
    if isinstance(t, sqltypes.Time):
        return "time"
    if isinstance(t, sqltypes.Float):
        return "float"
    if isinstance(t, sqltypes.Numeric):
        return "decimal"
    if isinstance(t, sqltypes.BigInteger):
        return "bigint"
    if isinstance(t, sqltypes.Integer):
        return "int"
    if isinstance(t, sqltypes.Text):
        return "text"
    if isinstance(t, sqltypes.String):
        return "string"
    return "other"


_COMPATIBLE = ({"uuid", "string", "text", "enum"}, {"bool", "int", "bigint"}, {"int", "bigint"},
               {"string", "text", "enum"}, {"float", "decimal"})


def same_kind(a: str, b: str) -> bool:
    """True when two type families store the same thing (sqlite keeps a UUID as text)."""
    return a == b or any(a in group and b in group for group in _COMPATIBLE)


# =============================================================================
# Server defaults
# =============================================================================

_NOW = re.compile(
    r"^(now\(\)|current_timestamp(\(\d*\))?|localtimestamp(\(\d*\))?|"
    r"statement_timestamp\(\)|transaction_timestamp\(\)|getdate\(\)|sysdate\(\)|"
    r"utc_timestamp\(\)|datetime\('now'(, *'localtime')?\))$",
    re.IGNORECASE,
)
_TODAY = re.compile(r"^(current_date(\(\))?|curdate\(\)|date\('now'(, *'localtime')?\))$", re.IGNORECASE)
_UUID_FN = re.compile(r"^(gen_random_uuid\(\)|uuid_generate_v4\(\)|uuid\(\))$", re.IGNORECASE)
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _unwrap(sql: str) -> str:
    s = sql.strip()
    while True:
        previous = s
        if s.startswith("(") and s.endswith(")") and _balanced(s[1:-1]):
            s = s[1:-1].strip()
        s = re.sub(r"::[A-Za-z_][A-Za-z0-9_ \"\[\]]*(\(\d+(, *\d+)?\))?$", "", s).strip()
        if s == previous:
            return s


def _balanced(s: str) -> bool:
    depth = 0
    for ch in s:
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            return False
    return depth == 0


def parse_default(sql: str, kind: str) -> tuple[str, str]:
    """Translates a server default into ``(mode, code)``.

    `mode` is ``py`` (`code` is a Python literal), ``now`` / ``today`` (the
    Ushka ``auto_now``), ``uuid`` (``uuid.uuid4``), ``serial`` (an
    auto-increment, nothing to map), ``none`` (``DEFAULT NULL``) or ``raw``
    (not understood: `code` is the original SQL, kept as ``server_default``).
    """
    s = _unwrap(sql)
    low = s.lower()
    if low == "null":
        return "none", ""
    if low.startswith("nextval("):
        return "serial", ""
    if _NOW.match(s):
        return "now", ""
    if _TODAY.match(s):
        return "today", ""
    if _UUID_FN.match(s):
        return "uuid", ""
    if kind == "bool":
        if low in ("true", "1", "b'1'", "'1'", "'t'", "'true'", "'y'"):
            return "py", "True"
        if low in ("false", "0", "b'0'", "'0'", "'f'", "'false'", "'n'"):
            return "py", "False"
        return "raw", sql
    m = re.fullmatch(r"'((?:[^']|'')*)'", s)
    if m:
        value = m.group(1).replace("''", "'")
        if kind in ("int", "bigint") and re.fullmatch(r"-?\d+", value):
            return "py", str(int(value))
        if kind in ("float", "decimal") and _NUMBER.match(value):
            return "py", value
        if kind in ("string", "text", "enum"):
            return "py", repr(value)
        if kind == "json" and value.replace(" ", "") in ("{}", "[]"):
            return "py", "dict" if value.strip().startswith("{") else "list"
        return "raw", sql
    if _NUMBER.match(s):
        if kind in ("int", "bigint"):
            return ("py", s) if "." not in s else ("raw", sql)
        if kind in ("float", "decimal"):
            return "py", s
        if kind in ("string", "text", "enum"):  # MySQL reports 'new' as new
            return "py", repr(s)
        return "raw", sql
    if kind in ("string", "text", "enum") and re.fullmatch(r"[A-Za-z0-9_ .-]+", s):
        return "py", repr(s)  # MySQL again: unquoted text
    return "raw", sql


# =============================================================================
# Code generation
# =============================================================================


def _singular(word: str) -> str:
    low = word.lower()
    if low.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if low.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if low.endswith(("ss", "us", "is")) or not low.endswith("s") or len(word) < 3:
        return word
    return word[:-1]


def class_name(table: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", table) if w]
    if not words:
        return "Table"
    words[-1] = _singular(words[-1])
    name = "".join(w[:1].upper() + w[1:] for w in words)
    return f"T{name}" if name[0].isdigit() else name


def _valid_attr(name: str) -> bool:
    return (
        name.isidentifier()
        and not keyword.iskeyword(name)
        and not name.startswith("_")
        and name not in RESERVED_ATTRS
    )


def _attr_name(name: str) -> str:
    if _valid_attr(name):
        return name
    base = re.sub(r"\W+", "_", name).strip("_") or "column"
    if base[0].isdigit():
        base = f"c_{base}"
    return base + "_" if (keyword.iskeyword(base) or base in RESERVED_ATTRS) else (
        base if _valid_attr(base) else f"c_{base}"
    )


class _Imports:
    def __init__(self) -> None:
        self.plain: set[str] = set()
        self.names: dict[str, set[str]] = {}

    def add(self, module: str, *names: str) -> None:
        self.names.setdefault(module, set()).update(names)

    def render(self) -> list[str]:
        lines = [f"import {m}" for m in sorted(self.plain)]
        for module in sorted(self.names):
            lines.append(f"from {module} import {', '.join(sorted(self.names[module]))}")
        return lines


class Generator:
    """Turns reflected tables into Ushka model source plus a list of `Finding`s."""

    def __init__(self, tables: list[TableInfo]) -> None:
        self.tables = tables
        self.findings: list[Finding] = []
        self.imports = _Imports()
        self.known = {t.name for t in tables}

    # -- public ---------------------------------------------------------------

    def generate(self) -> str:
        classes: list[str] = []
        used: set[str] = set()
        for table in self.tables:
            classes.append(self._table(table, used))
        header = [
            '"""Ushka models reflected from an existing database by `ushka db inspect`.',
            "",
            "Review every `TODO(ushka db inspect)` comment before you rely on these",
            "models: they mark what the database does not say (Python-side defaults,",
            "timestamps, ON DELETE) and guesses that need a human. Nothing risky was",
            'applied for you."""',
            "",
        ]
        self.imports.add("ushka.orm", "db")
        return "\n".join(header + self.imports.render() + ["", ""] + ["\n\n\n".join(classes)]) + "\n"

    # -- helpers ----------------------------------------------------------------

    def _find(self, kind: str, table: str, column: str | None, message: str, suggestion: str = "") -> Finding:
        f = Finding(kind, table, column, message, suggestion)
        self.findings.append(f)
        return f

    def _raw_type(self, t: Any) -> str:
        with contextlib.suppress(Exception):  # dialect types without a generic form
            t = t.as_generic()
        code = repr(t)
        for name in set(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", code)):
            if hasattr(sqltypes, name):
                self.imports.add("sqlalchemy", name)
            else:
                module = type(t).__module__
                for owner in (t, *getattr(t, "__dict__", {}).values()):
                    mod = type(owner).__module__ if not isinstance(owner, type) else owner.__module__
                    if mod.startswith("sqlalchemy.dialects"):
                        module = ".".join(mod.split(".")[:3])
                self.imports.add(module, name)
        return code

    def _table(self, t: TableInfo, used: set[str]) -> str:
        cname = class_name(t.name)
        while cname in used or keyword.iskeyword(cname) or cname in {"Column", "Index", "Model", "UniqueConstraint"}:
            cname += "Model"
        used.add(cname)

        by_name = {c.name: c for c in t.columns}
        std_pk = False
        if len(t.pk) == 1 and t.pk[0] == "id":
            col = by_name["id"]
            mode = parse_default(col.default, "int")[0] if col.default else "none"
            std_pk = (
                kind_of(col.type) in ("int", "bigint")
                and mode in ("none", "serial")
                and not any(fk.columns == ["id"] for fk in t.fks)
            )
        if not t.pk:
            self._find(
                "no-primary-key", t.name, None,
                "this table has no primary key, so it cannot be mapped as it is.",
                "Add a primary key to the table, or declare one of its columns with primary_key=True.",
            )
        base = "db.Model" if std_pk else "db.BaseModel"

        single_fk = {fk.columns[0]: fk for fk in t.fks if len(fk.columns) == 1}
        multi_fk = [fk for fk in t.fks if len(fk.columns) > 1]
        unique_single = {u.columns[0] for u in (*t.uniques, *(i for i in t.indexes if i.unique)) if len(u.columns) == 1}
        table_args: list[str] = []
        body: list[str] = []

        for col in t.columns:
            if std_pk and col.name == "id":
                continue
            lines = self._column(t, col, single_fk.get(col.name), col.name in unique_single, table_args)
            body.extend(lines)

        for fk in multi_fk:
            self.imports.add("sqlalchemy", "ForeignKeyConstraint")
            target = [self._target(fk, rc) for rc in fk.ref_columns]
            extra = "".join(
                f", {k}={v!r}" for k, v in (("ondelete", fk.ondelete), ("onupdate", fk.onupdate)) if v
            )
            table_args.append(f"ForeignKeyConstraint({fk.columns!r}, {target!r}{extra})")
            fkf = self._fk_finding(t.name, fk)
            if fkf:
                self.findings.append(fkf)
                body.extend(self._comment([fkf]))

        covered = {col for col in unique_single}
        for uq in (*t.uniques, *(i for i in t.indexes if i.unique)):
            if len(uq.columns) > 1 and not any(f"{uq.columns!r}" in a for a in table_args if a.startswith("UniqueConstraint")):
                self.imports.add("sqlalchemy", "UniqueConstraint")
                table_args.append(f"UniqueConstraint({', '.join(repr(c) for c in uq.columns)}"
                                  + (f", name={uq.name!r}" if uq.name else "") + ")")
        for ix in t.indexes:
            if ix.unique and len(ix.columns) == 1 and ix.columns[0] in covered:
                continue
            if any(c is None for c in ix.columns) or not ix.name:
                self._find(
                    "index", t.name, None,
                    f"index {ix.name or '(unnamed)'} is an expression index and was not mapped.",
                    "Add it by hand with sqlalchemy.Index if the models need it.",
                )
                continue
            if ix.unique and len(ix.columns) > 1:
                continue  # written as a UniqueConstraint above
            self.imports.add("sqlalchemy", "Index")
            table_args.append(
                f"Index({ix.name!r}, {', '.join(repr(c) for c in ix.columns)}" + (", unique=True" if ix.unique else "") + ")"
            )
        if t.schema:
            table_args.append(f"{{'schema': {t.schema!r}}}")

        out = [f"class {cname}({base}):", f"    __tablename__ = {t.name!r}"]
        if not t.pk:
            out.insert(1, f"    # TODO(ushka db inspect): {t.name} has no primary key; SQLAlchemy cannot map it until you add one.")
        out.append("")
        out.extend(body or ["    pass"])
        if table_args:
            out.append("")
            out.append("    __table_args__ = (")
            out.extend(f"        {a}," for a in table_args)
            out.append("    )")
        return "\n".join(out)

    def _target(self, fk: ForeignKeyInfo, ref_column: str) -> str:
        prefix = f"{fk.ref_schema}." if fk.ref_schema else ""
        return f"{prefix}{fk.ref_table}.{ref_column}"

    def _comment(self, findings: list[Finding]) -> list[str]:
        lines = []
        for f in findings:
            text = f.message + (f" Suggestion: {f.suggestion}" if f.suggestion else "")
            wrapped = textwrap.wrap(f"TODO(ushka db inspect): {text}", 92, subsequent_indent="  ")
            lines.extend(f"    # {w}" for w in wrapped)
        return lines

    # -- foreign keys ------------------------------------------------------------

    def _fk_finding(self, table: str, fk: ForeignKeyInfo) -> Finding | None:
        if fk.ondelete not in (None, "RESTRICT"):
            return None
        label = "NO ACTION" if fk.ondelete is None else "RESTRICT"
        first = fk.columns[0]
        f = Finding(
            "fk-on-delete", table, first,
            f"foreign key {table}({', '.join(fk.columns)}) -> {fk.ref_table}({', '.join(fk.ref_columns)}) "
            f"has no ON DELETE action in the database (currently {label}). Deleting a "
            f"{fk.ref_table} row that still has {table} rows fails with an IntegrityError "
            f"(or leaves orphans on a database that does not enforce foreign keys), and the old "
            f"ORM may have been deleting the children in Python.",
            "Delete the children first inside one db.Session() transaction, or change the "
            "constraint with a migration and set on_delete=db.CASCADE (or db.SET_NULL on a "
            "nullable column) here. Changing it here only does not alter the database.",
        )
        return f

    # -- columns -----------------------------------------------------------------

    def _column(self, t: TableInfo, col: ColumnInfo, fk: ForeignKeyInfo | None, unique: bool, table_args: list[str]) -> list[str]:
        kind = kind_of(col.type)
        attr = _attr_name(col.name)
        renamed = attr != col.name
        is_pk = col.name in t.pk
        composite_pk = len(t.pk) > 1
        findings: list[Finding] = []
        name = col.name.lower()
        temporal = kind in ("datetime", "date")

        mode, code = ("none", "")
        if col.default is not None:
            mode, code = parse_default(col.default, kind)
        if mode == "serial":
            mode = "none"
        if mode == "now" and kind != "datetime" and kind != "date":
            mode, code = "raw", col.default
        if mode == "today" and kind != "date":
            mode, code = "raw", col.default
        if mode == "uuid" and kind != "uuid":
            mode, code = "raw", col.default
        if mode == "now" and kind == "date":
            mode = "today"  # now() on a DATE column fills the current date

        has_default = mode != "none"
        if mode == "raw":
            findings.append(Finding(
                "server-default", t.name, col.name,
                f"the server default {col.default!r} could not be translated to Python, so it was kept as a server_default.",
                "Check it is what you want; the database keeps applying it either way.",
            ))
        elif has_default:
            shown = {"now": "auto_now=True", "today": "auto_now=True", "uuid": "default=uuid.uuid4"}.get(mode, f"default={code}")
            findings.append(Finding(
                "mapped-default", t.name, col.name,
                f"server default {col.default!r} was mapped to {shown}.",
                "Review it: the Python side now sends this value explicitly.",
            ))

        # Heuristic findings: what the database does not say.
        if (
            kind == "int"
            and getattr(col.type, "display_width", None) == 1
            and type(col.type).__name__ == "TINYINT"
        ):
            findings.append(Finding(
                "bool-like", t.name, col.name,
                "TINYINT(1) is how MySQL stores a boolean, but it was kept as an integer.",
                "Use db.Bool(...) if it is a flag.",
            ))
        if type(col.type).__name__ == "CHAR" and getattr(col.type, "length", None) in (32, 36):
            findings.append(Finding(
                "uuid-like", t.name, col.name,
                f"CHAR({col.type.length}) is how SQLite (and some ORMs) store a UUID, but it was kept as text.",
                "Use db.UUID(...) if the values are UUIDs, so they come back as uuid.UUID.",
            ))
        if temporal and name in _UPDATED:
            findings.append(Finding(
                "timestamp", t.name, col.name,
                "this looks like an 'updated' timestamp. The database does not refresh it on UPDATE: "
                "the old ORM probably set it in Python on every save, and Ushka's auto_now only fills "
                "the value on insert.",
                "Set it yourself before save() (e.g. datetime.now(timezone.utc)), or declare "
                "Column(DateTime, onupdate=func.now()); use auto_now=True for the insert value.",
            ))
        elif temporal and name in _CREATED and not has_default:
            findings.append(Finding(
                "timestamp", t.name, col.name,
                "this looks like a 'created' timestamp with no server default: the old ORM probably "
                "filled it in Python.",
                "Use auto_now=True so every insert gets the current time.",
            ))
        elif (
            not col.nullable and not has_default and not is_pk and fk is None
            and not col.autoincrement
            and kind in ("bool", "int", "bigint", "float", "decimal", "enum", "json", "datetime", "date", "time", "other")
        ):
            if kind == "bool":
                msg = ("NOT NULL boolean without a server default: the old ORM probably applied a Python "
                       "default (e.g. Django default=True), so without one here creating a row without this "
                       "field fails.")
                sug = "Set default=False or default=True, whichever the old code used."
            elif kind in ("int", "bigint", "float", "decimal"):
                msg = ("NOT NULL number without a server default: the old ORM may have applied a Python "
                       "default (often 0), so creating a row without it fails here.")
                sug = "Set default=0 (or the value the old code used) if rows are created without it."
            else:
                msg = "NOT NULL column without a server default: the old ORM may have applied a Python default."
                sug = "Add the default the old code used, if any."
            findings.append(Finding("not-null-no-default", t.name, col.name, msg, sug))

        # ---- decide the expression ---------------------------------------------
        expr = None
        if fk is not None:
            fkf = self._fk_finding(t.name, fk)
            if fkf:
                findings.append(fkf)
            helper_ok = (
                not renamed and not has_default and not unique and not is_pk
                and not (fk.ondelete == "SET NULL" and not col.nullable)
                and kind in ("int", "bigint", "string", "uuid")
            )
            if helper_ok:
                expr = self._fk_helper(col, fk, kind)
        else:
            expr = self._helper(col, kind, mode, code, unique, is_pk, composite_pk, renamed, table_args)
        if expr is None:
            expr = self._raw(col, kind, mode, code, unique, is_pk, composite_pk, fk, renamed)

        self.findings.extend(findings)
        out = self._comment([f for f in findings if f.kind not in ("mapped-default",)])
        mapped = [f for f in findings if f.kind == "mapped-default"]
        if mapped:
            out.extend(f"    # NOTE(ushka db inspect): {f.message}" for f in mapped)
        out.append(f"    {attr} = {expr}")
        return out

    def _fk_helper(self, col: ColumnInfo, fk: ForeignKeyInfo, kind: str) -> str:
        args = [repr(self._target(fk, fk.ref_columns[0]))]
        if kind == "int":
            args.append("dtype=db.Int()")
        elif kind == "uuid":
            args.append("dtype=db.UUID()")
        elif kind == "string":
            args.append(f"dtype=db.String(length={getattr(col.type, 'length', None)!r})")
        args.append(f"on_delete={self._action_code(fk.ondelete)}")
        if col.nullable:
            args.append("nullable=True")
        if fk.onupdate:
            args.append(f"on_update={fk.onupdate!r}")
        return f"db.ForeignKey({', '.join(args)})"

    @staticmethod
    def _action_code(action: str | None) -> str:
        return {None: "None", "CASCADE": "db.CASCADE", "SET NULL": "db.SET_NULL", "RESTRICT": "db.RESTRICT"}.get(
            action, repr(action)
        )

    def _helper(self, col, kind, mode, code, unique, is_pk, composite_pk, renamed, table_args) -> str | None:
        """The `db.*` helper call for a column, or None when it cannot say it.

        A helper is only used when it reproduces the database exactly. Several
        helpers carry a default of their own (``Bool`` is False, ``Float`` is
        0.0, ``JSON`` is {}); those are always written out, as ``None`` when
        the database has none, so nothing is filled in behind your back.
        """
        if renamed or mode == "raw":
            return None
        tz = getattr(col.type, "timezone", False)
        length = getattr(col.type, "length", None)
        nullable = ["nullable=True"] if col.nullable else []
        literal = [f"default={code}"] if mode == "py" else []
        uniq = ["unique=True"] if unique else []

        def call(name: str, *args: str) -> str:
            return f"db.{name}({', '.join(a for a in args if a)})"

        if is_pk:
            if kind == "uuid" and not composite_pk and mode in ("none", "uuid"):
                return "db.UUID(primary_key=True)"
            return None
        if kind == "uuid" and mode in ("none", "uuid"):
            default = []
            if mode == "uuid":
                self.imports.plain.add("uuid")
                default = ["default=uuid.uuid4"]
            return call("UUID", *default, *uniq, *nullable)
        if kind == "string" and mode in ("none", "py"):
            return call("String", f"length={length!r}", *uniq, *nullable, *literal)
        if kind == "text" and mode in ("none", "py") and not unique:
            return call("Text", *nullable, *literal)
        if kind in ("int", "bigint") and mode in ("none", "py"):
            return call("Int" if kind == "int" else "BigInt", *uniq, *nullable, *literal)
        if kind == "float" and mode in ("none", "py") and not unique:
            return call("Float", f"default={code if mode == 'py' else None}", *nullable)
        if kind == "decimal" and mode in ("none", "py") and not unique:
            p, sc = getattr(col.type, "precision", None), getattr(col.type, "scale", None)
            if p is None or sc is None:
                return None
            return call("Decimal", f"precision={p}", f"scale={sc}", f"default={code if mode == 'py' else None}", *nullable)
        if kind == "bool" and mode in ("none", "py") and not unique:
            return call("Bool", f"default={code if mode == 'py' else None}", *nullable)
        if kind == "json" and mode == "py" and code in ("dict", "list") and not unique:
            return call("JSON", f"default={code}", *nullable)
        if kind == "binary" and mode == "none" and not unique:
            return call("Binary", f"length={length!r}", *nullable)
        if kind in ("datetime", "date") and mode in ("none", "now", "today") and not tz:
            if unique:
                self.imports.add("sqlalchemy", "UniqueConstraint")
                table_args.append(f"UniqueConstraint({col.name!r})")
            auto = ["auto_now=True"] if mode in ("now", "today") else []
            return call("DateTime" if kind == "datetime" else "Date", *auto, *nullable)
        if kind == "time" and mode == "none" and not unique and not tz:
            return call("Time", *nullable)
        return None

    def _raw(self, col, kind, mode, code, unique, is_pk, composite_pk, fk, renamed) -> str:
        """A plain SQLAlchemy ``Column``: always able to say exactly what the database has."""
        self.imports.add("sqlalchemy", "Column")
        parts = []
        if renamed:
            parts.append(repr(col.name))
        parts.append(self._raw_type(col.type))
        if fk is not None:
            self.imports.add("sqlalchemy", "ForeignKey")
            extra = "".join(
                f", {k}={v!r}" for k, v in (("ondelete", fk.ondelete), ("onupdate", fk.onupdate)) if v
            )
            parts.append(f"ForeignKey({self._target(fk, fk.ref_columns[0])!r}{extra})")
        if is_pk:
            parts.append("primary_key=True")
            if kind not in ("int", "bigint") or composite_pk:
                parts.append("autoincrement=False")
        else:
            parts.append(f"nullable={col.nullable}")
        if unique:
            parts.append("unique=True")
        if mode == "py":
            parts.append(f"default={code}")
        elif mode == "now":
            self.imports.add("sqlalchemy", "func")
            parts.append("default=func.now()")
        elif mode == "today":
            self.imports.add("sqlalchemy", "func")
            parts.append("default=func.current_date()")
        elif mode == "uuid":
            self.imports.plain.add("uuid")
            parts.append("default=uuid.uuid4")
        elif mode == "raw":
            self.imports.add("sqlalchemy", "text")
            parts.append(f"server_default=text({code!r})")
        return f"Column({', '.join(parts)})"


def generate(tables: list[TableInfo]) -> tuple[str, list[Finding]]:
    """Returns ``(source, findings)`` for the reflected `tables`."""
    gen = Generator(tables)
    source = gen.generate()
    return source, gen.findings


# =============================================================================
# Comparing the models with the database
# =============================================================================


@dataclass
class Divergence:
    table: str
    column: str | None
    message: str

    def where(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table


def compare(database: list[TableInfo], models: list[TableInfo]) -> list[Divergence]:
    """Lists where the models and the database disagree.

    Checks tables, columns, nullability, type families and the ON DELETE /
    ON UPDATE of foreign keys. Tables that have no model are not reported.
    """
    out: list[Divergence] = []
    db_by = {t.name: t for t in database}
    for mt in models:
        dt = db_by.get(mt.name)
        if dt is None:
            out.append(Divergence(mt.name, None, "the model has no table in the database (run ushka db make / migrate)."))
            continue
        dcols = {c.name: c for c in dt.columns}
        mcols = {c.name: c for c in mt.columns}
        for name, mc in mcols.items():
            dc = dcols.get(name)
            if dc is None:
                out.append(Divergence(mt.name, name, "in the model, missing in the database."))
                continue
            if mc.nullable != dc.nullable:
                out.append(Divergence(
                    mt.name, name,
                    f"nullable is {mc.nullable} in the model but {dc.nullable} in the database.",
                ))
            mk, dk = kind_of(mc.type), kind_of(dc.type)
            if "other" not in (mk, dk) and not same_kind(mk, dk):
                out.append(Divergence(mt.name, name, f"type is {mk} in the model but {dk} in the database."))
        for name, dc in dcols.items():
            if name not in mcols:
                breaks = not dc.nullable and dc.default is None and not dc.autoincrement and name not in dt.pk
                out.append(Divergence(
                    mt.name, name,
                    "in the database, missing in the model"
                    + (": it is NOT NULL without a default, so every insert from the model fails." if breaks else "."),
                ))
        mfks = {(tuple(f.columns), f.ref_table): f for f in mt.fks}
        dfks = {(tuple(f.columns), f.ref_table): f for f in dt.fks}
        for key, mf in mfks.items():
            df = dfks.get(key)
            label = f"{', '.join(key[0])} -> {key[1]}"
            if df is None:
                out.append(Divergence(mt.name, key[0][0], f"foreign key {label} is in the model, not in the database."))
            else:
                for what, a, b in (("ON DELETE", mf.ondelete, df.ondelete), ("ON UPDATE", mf.onupdate, df.onupdate)):
                    if a != b:
                        out.append(Divergence(
                            mt.name, key[0][0],
                            f"foreign key {label}: {what} is {a or 'NO ACTION'} in the model but "
                            f"{b or 'NO ACTION'} in the database.",
                        ))
        for key, df in dfks.items():
            if key not in mfks:
                out.append(Divergence(
                    mt.name, key[0][0],
                    f"foreign key {', '.join(key[0])} -> {key[1]} is in the database "
                    f"(ON DELETE {df.ondelete or 'NO ACTION'}), not in the model.",
                ))
    return out
