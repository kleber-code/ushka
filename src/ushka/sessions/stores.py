"""
Where server-side sessions live.

With `[session] store = "database"` (or an object you assign to
``app.session_store``) the session cookie carries only an opaque,
signed id and the data stays here. Deleting a record revokes the session for
real: a stolen cookie stops working.

The database store needs a database: ``[database] url`` (or ``DATABASE_URL``)
must be set and SQLAlchemy installed (``ushka[orm]``). Without one the app
keeps using signed cookies and says so in the log. There is no in-process store
on purpose: it would log users out at random as soon as there is more than one
worker.

A store is a small class, `SessionStore`. Subclass it to keep sessions in
Redis or anywhere else; the framework only calls the methods below.
Nothing in a store is ever logged.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("ushka")

__all__ = [
    "DatabaseStore",
    "SessionRecord",
    "SessionStore",
    "get_store",
    "no_database_reason",
    "revoke_user_sessions",
]


@dataclass
class SessionRecord:
    """One stored session.

    Attributes
    ----------
    key : str
        SHA-256 of the session id. The id itself is never stored, so a leaked
        database or backup cannot be turned into working cookies.
    data : str
        The session contents as JSON text.
    user_id : str or None
        Who the session belongs to (the value of ``[session] user_key``).
    created_at, last_seen : float
        Unix times, used for the absolute and the idle expiry.
    """

    key: str
    data: str
    user_id: str | None
    created_at: float
    last_seen: float


class SessionStore:
    """Base class of a session store. Every method is a coroutine.

    Implement `load`, `save`, `touch`, `delete` and `delete_user`; `purge` is
    optional (stores with their own expiry, such as Redis, can skip it).
    """

    async def load(self, key: str) -> SessionRecord | None:
        """Returns the record stored under `key`, or None."""
        raise NotImplementedError

    async def save(self, record: SessionRecord) -> None:
        """Inserts or replaces the record."""
        raise NotImplementedError

    async def touch(self, key: str, last_seen: float) -> None:
        """Updates ``last_seen`` of an existing record; never creates one."""
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        """Removes the record. Missing keys are not an error."""
        raise NotImplementedError

    async def delete_user(self, user_id: str) -> int:
        """Removes every record of `user_id` and returns how many there were."""
        raise NotImplementedError

    async def close(self) -> None:
        """Releases connections. Called when the app shuts down; the default does nothing."""

    async def purge(self, created_before: float | None, seen_before: float | None) -> int:
        """Removes expired records (created before `created_before` or idle
        since `seen_before`; None means no such limit). Returns the count."""
        return 0


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class DatabaseStore(SessionStore):
    """Sessions in a table of the `[database]` database (SQLAlchemy, async).

    The table is created on first use; its name is ``[session] table``. It
    needs the ``orm`` extra (``pip install "ushka[orm]"``).
    """

    def __init__(self, url: str, table: str = "ushka_sessions") -> None:
        if not _IDENT.match(table):
            raise ValueError(f"[session] table must be a plain SQL name, got {table!r}")
        try:
            import sqlalchemy as sa
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise RuntimeError('[session] store = "database" needs the orm extra: pip install "ushka[orm]"') from exc
        from ushka.orm.database import UshkaDB

        self._sa = sa
        self._engine = create_async_engine(UshkaDB.to_async_url(url), echo=False)
        meta = sa.MetaData()
        self._table = sa.Table(
            table,
            meta,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(255), nullable=True, index=True),
            sa.Column("data", sa.Text, nullable=False),
            sa.Column("created_at", sa.Float, nullable=False),
            sa.Column("last_seen", sa.Float, nullable=False),
        )
        self._meta = meta
        self._ready = False
        self._lock = asyncio.Lock()

    async def _setup(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                async with self._engine.begin() as conn:
                    await conn.run_sync(self._meta.create_all)
                self._ready = True

    async def load(self, key: str) -> SessionRecord | None:
        await self._setup()
        t = self._table
        async with self._engine.connect() as conn:
            row = (await conn.execute(self._sa.select(t).where(t.c.id == key))).first()
        if row is None:
            return None
        return SessionRecord(row.id, row.data, row.user_id, row.created_at, row.last_seen)

    async def save(self, record: SessionRecord) -> None:
        await self._setup()
        t, sa = self._table, self._sa
        values = {
            "user_id": record.user_id,
            "data": record.data,
            "created_at": record.created_at,
            "last_seen": record.last_seen,
        }
        async with self._engine.begin() as conn:
            result = await conn.execute(sa.update(t).where(t.c.id == record.key).values(**values))
            if result.rowcount:
                return
        try:
            async with self._engine.begin() as conn:
                await conn.execute(sa.insert(t).values(id=record.key, **values))
        except sa.exc.IntegrityError:  # another request inserted it first
            async with self._engine.begin() as conn:
                await conn.execute(sa.update(t).where(t.c.id == record.key).values(**values))

    async def touch(self, key: str, last_seen: float) -> None:
        await self._setup()
        t = self._table
        async with self._engine.begin() as conn:
            await conn.execute(self._sa.update(t).where(t.c.id == key).values(last_seen=last_seen))

    async def delete(self, key: str) -> None:
        await self._setup()
        t = self._table
        async with self._engine.begin() as conn:
            await conn.execute(self._sa.delete(t).where(t.c.id == key))

    async def delete_user(self, user_id: str) -> int:
        await self._setup()
        t = self._table
        async with self._engine.begin() as conn:
            result = await conn.execute(self._sa.delete(t).where(t.c.user_id == user_id))
        return result.rowcount or 0

    async def close(self) -> None:
        await self._engine.dispose()

    async def purge(self, created_before: float | None, seen_before: float | None) -> int:
        await self._setup()
        t, sa = self._table, self._sa
        conditions = []
        if created_before is not None:
            conditions.append(t.c.created_at < created_before)
        if seen_before is not None:
            conditions.append(t.c.last_seen < seen_before)
        if not conditions:
            return 0
        async with self._engine.begin() as conn:
            result = await conn.execute(sa.delete(t).where(sa.or_(*conditions)))
        return result.rowcount or 0


def get_store(app: Any) -> SessionStore | None:
    """The store the app uses, or None when sessions are signed cookies.

    ``app.session_store`` wins when it is set; otherwise the store named by
    ``[session] store`` is built once and kept on the app.
    """
    store = getattr(app, "session_store", None)
    if store is not None:
        return store
    kind = str(app.config.get("session_store", "cookie") or "cookie").lower()
    if kind == "cookie":
        return None
    if kind != "database":
        raise ValueError(f'[session] store must be "cookie" or "database", got {kind!r}')
    reason = no_database_reason(app.config)
    if reason:
        if not getattr(app, "_session_fallback_logged", False):
            app._session_fallback_logged = True
            log.warning('[session] store = "database" needs a database, so sessions stay signed cookies '
                        "(not revocable on the server): %s.", reason)
        return None
    store = DatabaseStore(app.config.get("database_url"), app.config.get("session_table", "ushka_sessions"))
    app.session_store = store
    return store


def no_database_reason(config: Any) -> str:
    """Why server-side sessions cannot use a database, or an empty string when they can."""
    if config.source_of("database_url") == "default":
        return "no database is configured: set [database] url or DATABASE_URL"
    if importlib.util.find_spec("sqlalchemy") is None:
        return "SQLAlchemy is not installed: pip install 'ushka[orm]'"
    return ""


async def revoke_user_sessions(target: Any, user_id: Any) -> int:
    """Logs `user_id` out everywhere: deletes all their server-side sessions.

    `target` is the app or the current request. Returns how many sessions were
    removed. When it is a request whose own session belongs to that user, that
    session is cleared too, so this response does not write it back.
    """
    app = getattr(target, "app", target)
    store = get_store(app)
    if store is None:
        raise RuntimeError('revoke_user_sessions needs server-side sessions: set [session] store = "database" and configure a database.')
    count = await store.delete_user(str(user_id))
    session = getattr(target, "_cached_data", {}).get("session")
    if session is not None and hasattr(session, "revoke") and session.user_id == str(user_id):
        session.revoke()
    return count
