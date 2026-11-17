"""
This module provides an asynchronous Object-Relational Mapper (ORM) for the
Ushka framework, built on top of SQLAlchemy 2.0.

It includes the `UshkaDB` manager for engine and session handling, a dynamically
generated `BaseModel` with Active Record-style CRUD operations, and helper
methods for defining common SQLAlchemy column types.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import datetime as _dt
import enum
import uuid
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import sqlalchemy.types as sqltypes
from sqlalchemy import Column, ForeignKey, MetaData, event, inspect, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

from ushka.guard import check_sql, is_template
from ushka.guard.templates import sql as template_to_sql

# =============================================================================
# NAMING CONVENTION
# =============================================================================
# Ensures compatibility with SQLite Batch migrations by naming all constraints.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_metadata = MetaData(naming_convention=NAMING_CONVENTION)
_Base = declarative_base(metadata=_metadata)

# Type variable bound to _Base, allows for generic typing of the dynamic
# BaseModel while avoiding 'undefined name' (F821) linting errors.
T = TypeVar("T", bound=_Base)


def utcnow() -> _dt.datetime:
    """The current time as an aware ``datetime`` in UTC (what ``auto_now`` stores)."""
    return _dt.datetime.now(_dt.timezone.utc)


def _utcnow_naive() -> _dt.datetime:
    return utcnow().replace(tzinfo=None)


class UTCDateTime(sqltypes.TypeDecorator):
    """A timezone-aware ``DateTime`` that always reads back as UTC.

    PostgreSQL stores ``timestamptz``. SQLite and MySQL drop the offset, so a
    naive value read from them is taken as UTC and given ``tzinfo=UTC``;
    an aware value is converted to UTC before it is written.
    """

    impl = sqltypes.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, _dt.datetime) and value.tzinfo is not None:
            value = value.astimezone(_dt.timezone.utc)
            if dialect.name in ("sqlite", "mysql", "mariadb"):
                value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, _dt.datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=_dt.timezone.utc)
            return value.astimezone(_dt.timezone.utc)
        return value


def _sqlite_explicit_begin(engine) -> None:
    """Make SQLite begin transactions when SQLAlchemy says so.

    The sqlite3 driver only opens a transaction before the first INSERT,
    UPDATE or DELETE, so a SAVEPOINT that comes first would be the outermost
    one and its RELEASE would commit. This is the recipe from the SQLAlchemy
    docs ("Serializable isolation / Savepoints / Transactional DDL").
    """

    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")


class UshkaDB:
    """
    Asynchronous Database Manager for the Ushka Framework.

    Handles engine creation, session management, and provides the declarative
    Model base with built-in async Active Record methods.

    Attributes
    ----------
    CASCADE : str
        SQL ON DELETE CASCADE action.
    SET_NULL : str
        SQL ON DELETE SET NULL action.
    RESTRICT : str
        SQL ON DELETE RESTRICT action.
    url : str
        The database connection URL.
    engine : sqlalchemy.ext.asyncio.AsyncEngine
        The asynchronous SQLAlchemy engine.
    session_factory : async_sessionmaker
        Factory for creating new async sessions.
    Session : async_sessionmaker
        Factory of independent async sessions (``async with db.Session() as s``).
    metadata : sqlalchemy.MetaData
        The metadata object used by the declarative base.
    Model : Type[_Base]
        The model base: CRUD methods and a default ``id`` primary key.
    BaseModel : Type[_Base]
        The same base without the default ``id`` (declare your own key).
    """

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    RESTRICT = "RESTRICT"

    # Plain URLs are mapped to the async driver each backend needs.
    ASYNC_DRIVERS = {
        "sqlite": "sqlite+aiosqlite",
        "postgresql": "postgresql+asyncpg",
        "postgres": "postgresql+asyncpg",
        "mysql": "mysql+aiomysql",
    }

    def __init__(self, url: str | None = None):
        """
        Initializes the database manager.

        The engine is created lazily, on first use, from `url` or, when it is
        omitted, from the application config (``[database] url`` in
        ``ushka.toml``, ``USHKA_DATABASE_URL`` or ``DATABASE_URL``). This is
        the same setting the ``ushka db`` migration commands read, so the app
        and its migrations always target the same database.
        """
        self._url = url
        self._engine = None
        self._session_factory = None
        # (session, owning task) of the open `transaction()` of this context.
        self._tx: contextvars.ContextVar = contextvars.ContextVar(
            f"ushka_orm_tx_{id(self)}", default=None
        )
        self.metadata = _Base.metadata
        self.BaseModel, self.Model = self._create_model_base()

    @classmethod
    def to_async_url(cls, url: str) -> str:
        """Returns `url` with an async driver (``sqlite://`` → ``sqlite+aiosqlite://``)."""
        scheme, sep, rest = url.partition("://")
        if not sep or "+" in scheme:
            return url
        return f"{cls.ASYNC_DRIVERS.get(scheme, scheme)}://{rest}"

    @property
    def url(self) -> str:
        """The async database URL in use."""
        if self._url is None:
            from ushka.core.config import Config

            self._url = Config().get("database_url") or "sqlite:///ushka.db"
        return self.to_async_url(self._url)

    def configure(self, url: str) -> None:
        """Points the manager at another database (call before first use)."""
        self._url = url
        self._engine = self._session_factory = None

    @property
    def engine(self):
        """The `AsyncEngine`, created on first access."""
        if self._engine is None:
            self._engine = create_async_engine(self.url, echo=False)
            if self._engine.dialect.name == "sqlite":
                _sqlite_explicit_begin(self._engine.sync_engine)
        return self._engine

    @property
    def session_factory(self):
        """Factory for new `AsyncSession` objects."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine, class_=AsyncSession, expire_on_commit=False
            )
        return self._session_factory

    @property
    def Session(self):
        """Factory of new `AsyncSession` objects: ``async with db.Session() as s:``.

        Each call opens an independent session. (A task-scoped registry was used
        before; it was never cleared, so it leaked one session per request, and
        nested calls in the same task closed each other's session.)
        """
        return self.session_factory

    # --- TRANSACTIONS ---

    def _active(self):
        """The session of the open `transaction()` in this task, or None.

        A task spawned inside the block (``asyncio.gather``, ``create_task``)
        inherits the context variable, but an `AsyncSession` must not be
        used by two tasks at once, so only the task that opened the block
        sees it; the others keep using a session per call.
        """
        state = self._tx.get()
        if state is None:
            return None
        session, owner = state
        return session if owner is asyncio.current_task() else None

    @property
    def in_transaction(self) -> bool:
        """True inside ``async with db.transaction()`` (in the task that opened it)."""
        return self._active() is not None

    @contextlib.asynccontextmanager
    async def _use_session(self) -> AsyncIterator[AsyncSession]:
        """The transaction's session when there is one, else a short-lived one."""
        session = self._active()
        if session is not None:
            yield session
        else:
            async with self.Session() as own:
                yield own

    async def _commit(self, session: AsyncSession) -> None:
        """Commit a call-scoped session; only flush one owned by `transaction()`."""
        if session is self._active():
            await session.flush()
        else:
            await session.commit()

    @contextlib.asynccontextmanager
    async def transaction(self, *, savepoint: bool = True) -> AsyncIterator[AsyncSession]:
        """Runs several operations as one atomic unit.

        ``async with db.transaction():`` opens one session; inside it
        ``Model.create/save/delete/get/filter/...`` and ``db.execute`` all use
        it. The block commits when it ends and rolls everything back when it
        raises. Outside a block each call still opens and commits its own session.

        Nested blocks run in a SAVEPOINT: if the inner block raises, only its
        changes are undone, and the outer transaction carries on if you catch
        the error. Pass ``savepoint=False`` to join the outer transaction
        instead (the inner block then neither commits nor rolls back by itself).

        The session lives in a context variable, so concurrent requests and
        tasks never see each other's transaction; a task spawned inside the
        block does not use it either.

        Yields
        ------
        AsyncSession
            The transaction's session, for anything the Active Record methods
            do not cover.
        """
        outer = self._active()
        if outer is not None:
            if savepoint:
                async with outer.begin_nested():
                    yield outer
            else:
                yield outer
            return
        async with self.Session() as session:
            token = self._tx.set((session, asyncio.current_task()))
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
            finally:
                self._tx.reset(token)

    atomic = transaction

    def _create_model_base(self):
        """
        Creates the dynamic BaseModel class linked to this DB instance.

        Returns
        -------
        Type[_Base]
            The dynamically created BaseModel class.
        """
        db = self

        class BaseModel(_Base):
            """
            Model base without a default key: declare your own primary key.

            This class provides Active Record pattern methods for persistence
            and querying using asynchronous SQLAlchemy 2.0 style.

            ``class Meta: extend_existing = True`` lets a model describe a table
            that is already in the metadata (a mirrored or reflected schema).
            """

            __abstract__ = True

            def __init_subclass__(cls, **kw):
                super().__init_subclass__(**kw)
                meta = getattr(cls, "Meta", None)
                if (
                    cls.__dict__.get("__abstract__")
                    or not getattr(meta, "extend_existing", False)
                ):
                    return
                args = getattr(cls, "__table_args__", None)
                if args is None:
                    args = {}
                if isinstance(args, dict):
                    args = {**args, "extend_existing": True}
                else:
                    tail = args[-1] if args and isinstance(args[-1], dict) else {}
                    head = args[:-1] if tail else tuple(args)
                    args = (*head, {**tail, "extend_existing": True})
                cls.__table_args__ = args

            # --- INSTANCE METHODS ---

            async def save(self: T) -> T:
                """
                Persists the current instance to the database.

                If the instance is new, it is inserted; otherwise, it is updated.
                The instance is refreshed after commit.

                Returns
                -------
                T
                    The refreshed instance of the model.
                """
                async with db._use_session() as session:
                    session.add(self)
                    await db._commit(session)
                    await session.refresh(self)
                    return self

            async def delete(self) -> None:
                """
                Removes the current instance from the database.
                """
                async with db._use_session() as session:
                    await session.delete(self)
                    await db._commit(session)

            def to_dict(self) -> dict:
                """
                Serializes the model to a dictionary.

                This is synchronous as it operates on loaded memory data.
                Handles serialization of common types like Enum and UUID.

                Returns
                -------
                dict
                    A dictionary representation of the model's columns.
                """
                data = {}
                try:
                    mapper = inspect(self).mapper
                    for c in mapper.column_attrs:
                        val = getattr(self, c.key)
                        if isinstance(val, enum.Enum):
                            val = val.value
                        elif isinstance(val, uuid.UUID):
                            val = str(val)
                        data[c.key] = val
                except Exception:
                    # Fallback for detached or transient objects
                    return self.__dict__.copy()
                return data

            @classmethod
            async def create(cls: type[T], **kwargs) -> T:
                """
                Creates a new instance and saves it to the database.

                Parameters
                ----------
                **kwargs
                    Keyword arguments corresponding to model attributes.

                Returns
                -------
                T
                    The newly created and persisted instance.
                """
                instance = cls(**kwargs)
                return await instance.save()

            # --- QUERY METHODS ---

            @classmethod
            async def all(cls: type[T]) -> list[T]:
                """
                Returns all records for this model.

                Returns
                -------
                List[T]
                    A list of all model instances.
                """
                async with db._use_session() as session:
                    result = await session.execute(select(cls))
                    return result.scalars().all()

            @classmethod
            async def get(cls: type[T], id: Any) -> T | None:
                """
                Retrieves a single record by its Primary Key.

                Parameters
                ----------
                id : Any
                    The primary key value of the record to retrieve.

                Returns
                -------
                Optional[T]
                    The model instance if found, otherwise None.
                """
                async with db._use_session() as session:
                    return await session.get(cls, id)

            @classmethod
            async def first(cls: type[T], **kwargs) -> T | None:
                """
                Returns the first record matching the filters.

                Parameters
                ----------
                **kwargs
                    Keyword arguments used for filtering (e.g., `filter_by`).

                Returns
                -------
                Optional[T]
                    The first matching model instance if found, otherwise None.
                """
                async with db._use_session() as session:
                    stmt = select(cls).filter_by(**kwargs)
                    result = await session.execute(stmt)
                    return result.scalars().first()

            @classmethod
            async def filter(cls: type[T], **kwargs) -> list[T]:
                """
                Returns a list of records matching the filters.

                Parameters
                ----------
                **kwargs
                    Keyword arguments used for filtering (e.g., `filter_by`).

                Returns
                -------
                List[T]
                    A list of matching model instances.
                """
                async with db._use_session() as session:
                    stmt = select(cls).filter_by(**kwargs)
                    result = await session.execute(stmt)
                    return result.scalars().all()

            # --- SQLALCHEMY 2.0 HELPERS ---

            @classmethod
            def select(cls):
                """
                Returns a raw SQLAlchemy Select statement for this model.

                Usage: ``await db.execute(User.select().where(...))``

                Returns
                -------
                sqlalchemy.sql.Select
                    A SQLAlchemy Select construct targeting this model.
                """
                return select(cls)

            def __repr__(self):
                """
                Returns a string representation of the model instance.
                """
                try:
                    ident = inspect(self).identity
                except Exception:
                    ident = None
                pk = ", ".join(map(str, ident)) if ident else "No-ID"
                return f"<{self.__class__.__name__} {pk}>"

        class Model(BaseModel):
            """Model base with an auto-incrementing ``id`` primary key."""

            __abstract__ = True
            # SQLite only auto-increments an `INTEGER PRIMARY KEY`; a BIGINT
            # key stays NULL and every insert fails. 64-bit elsewhere.
            # A subclass that declares its own `id` replaces this column.
            id = Column(
                sqltypes.BigInteger().with_variant(sqltypes.Integer(), "sqlite"),
                primary_key=True,
                index=True,
                autoincrement=True,
            )

        return BaseModel, Model

    # --- EXECUTION HELPERS ---

    @staticmethod
    def text(sql: str, **params: Any):
        """Guarded ``sqlalchemy.text()``: refuses SQL built from request data.

        ``sqlalchemy.text()`` copies the string through ``re.sub``, which drops
        the `Untrusted` mark, so the check has to happen before the call. Use
        this (or pass the string to `execute`) instead of importing ``text``.

        Parameters
        ----------
        sql : str
            The SQL with ``:name`` placeholders.
        **params
            Values bound to the placeholders (never pasted into the SQL).
        """
        check_sql(sql)
        clause = text(sql)
        return clause.bindparams(**params) if params else clause

    async def execute(self, stmt):
        """
        Executes a raw SQL statement or SQLAlchemy construct using a session.

        Parameters
        ----------
        stmt : Any
            A SQLAlchemy executable construct (e.g., Select, Insert, raw text).

        Returns
        -------
        sqlalchemy.engine.Result
            The result object from the execution.

        Raises
        ------
        UnsafeValueError
            If the SQL text is `Untrusted` (built from request data). Use
            bound parameters, or a t-string on Python 3.14+, which binds every
            interpolated value automatically:
            ``await db.execute(t"SELECT * FROM users WHERE id = {user_id}")``.
        """
        if is_template(stmt):
            query, params = template_to_sql(stmt)
            stmt = text(query).bindparams(**params)
        elif isinstance(stmt, str):
            stmt = self.text(stmt)
        async with self._use_session() as session:
            return await session.execute(stmt)

    # --- TYPE HELPERS ---

    def String(
        self,
        length=255,
        unique=False,
        nullable=False,
        default=None,
        choices: list = None,
    ) -> Column:
        """
        Defines a SQLAlchemy String column.

        Parameters
        ----------
        length : int, optional
            Maximum length of the string. By default 255.
        unique : bool, optional
            If True, enforces uniqueness constraint. By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : Any, optional
            Default value for the column. By default None.
        choices : list, optional
            If provided, converts the column to a SQLAlchemy Enum type
            using the list elements as valid values. By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        type_engine = sqltypes.String(length)
        if choices:
            type_engine = sqltypes.Enum(
                *choices, name=None, native_enum=False, length=length
            )
        return Column(type_engine, unique=unique, nullable=nullable, default=default)

    def UUID(
        self, unique=False, nullable=False, primary_key=False, default=None
    ) -> Column:
        """
        Defines a SQLAlchemy UUID column.

        If `primary_key` is True and `default` is None, `uuid.uuid4` is used
        as the default generator.

        Parameters
        ----------
        unique : bool, optional
            If True, enforces uniqueness constraint. By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        primary_key : bool, optional
            If True, sets this column as the primary key. By default False.
        default : Any, optional
            Default value or callable for the column. By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        if primary_key and default is None:
            default = uuid.uuid4
        return Column(
            sqltypes.Uuid(as_uuid=True),
            primary_key=primary_key,
            unique=unique,
            nullable=nullable,
            default=default,
            index=primary_key,
        )

    def Text(self, nullable=False, default=None) -> Column:
        """
        Defines a SQLAlchemy Text column (for long strings).

        Parameters
        ----------
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : Any, optional
            Default value for the column. By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(sqltypes.Text, nullable=nullable, default=default)

    def Int(self, unique=False, nullable=False, default=None) -> Column:
        """
        Defines a SQLAlchemy Integer column.

        Parameters
        ----------
        unique : bool, optional
            If True, enforces uniqueness constraint. By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : Any, optional
            Default value for the column. By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(
            sqltypes.Integer, unique=unique, nullable=nullable, default=default
        )

    def BigInt(self, unique=False, nullable=False, default=None) -> Column:
        """
        Defines a SQLAlchemy BigInteger column.

        Parameters
        ----------
        unique : bool, optional
            If True, enforces uniqueness constraint. By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : Any, optional
            Default value for the column. By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(
            sqltypes.BigInteger, unique=unique, nullable=nullable, default=default
        )

    def Float(self, nullable=False, default=0.0) -> Column:
        """
        Defines a SQLAlchemy Float column.

        Parameters
        ----------
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : float, optional
            Default value for the column. By default 0.0.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(sqltypes.Float, nullable=nullable, default=default)

    def Decimal(self, precision=10, scale=2, nullable=False, default=0) -> Column:
        """
        Defines a SQLAlchemy Numeric/Decimal column.

        Parameters
        ----------
        precision : int, optional
            Total number of digits. By default 10.
        scale : int, optional
            Number of digits after the decimal point. By default 2.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : int or float, optional
            Default value for the column. By default 0.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(
            sqltypes.Numeric(precision, scale), nullable=nullable, default=default
        )

    def Bool(self, default=False, nullable=False) -> Column:
        """
        Defines a SQLAlchemy Boolean column.

        Parameters
        ----------
        default : bool, optional
            Default value for the column. By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(sqltypes.Boolean, nullable=nullable, default=default)

    def DateTime(
        self,
        auto_now=False,
        nullable=False,
        auto_now_add=False,
        timezone: bool | None = None,
    ) -> Column:
        """
        Defines a SQLAlchemy DateTime column.

        Parameters
        ----------
        auto_now : bool, optional
            If True, the ORM sets the current UTC time on insert and again on
            every update (an ``updated_at`` column). By default False.
        auto_now_add : bool, optional
            If True, the ORM sets the current UTC time on insert only (a
            ``created_at`` column). By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        timezone : bool, optional
            Store a timezone-aware value (``timestamptz`` on PostgreSQL; read
            back as UTC everywhere). Defaults to True for the automatic
            columns and False for a plain one.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        auto = auto_now or auto_now_add
        aware = auto if timezone is None else timezone
        stamp = utcnow if aware else _utcnow_naive
        return Column(
            UTCDateTime() if aware else sqltypes.DateTime,
            nullable=nullable,
            default=stamp if auto else None,
            onupdate=stamp if auto_now else None,
        )

    def Date(self, auto_now=False, nullable=False) -> Column:
        """
        Defines a SQLAlchemy Date column.

        Parameters
        ----------
        auto_now : bool, optional
            If True, sets the default value to the current database date (func.current_date()).
            By default False.
        nullable : bool, optional
            If True, allows NULL values. By default False.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(
            sqltypes.Date, nullable=nullable, default=func.current_date() if auto_now else None
        )

    def Time(self, nullable=False) -> Column:
        """
        Defines a SQLAlchemy Time column.

        Parameters
        ----------
        nullable : bool, optional
            If True, allows NULL values. By default False.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(sqltypes.Time, nullable=nullable)

    def JSON(self, nullable=False, default=None) -> Column:
        """
        Defines a SQLAlchemy JSON column.

        Parameters
        ----------
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : Any, optional
            Default value for the column. If None, defaults to an empty dictionary {}.
            By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        # A callable default gives every row its own dict; a literal `{}` would
        # be one object shared (and mutated) across all rows.
        if default is None:
            default_val = dict
        elif isinstance(default, (dict, list)):
            snapshot = default
            default_val = lambda: type(snapshot)(snapshot)
        else:
            default_val = default
        return Column(sqltypes.JSON, nullable=nullable, default=default_val)

    def Enum(self, enum_cls: type[enum.Enum], nullable=False, default=None) -> Column:
        """
        Defines a SQLAlchemy Enum column based on a Python Enum class.

        Parameters
        ----------
        enum_cls : Type[enum.Enum]
            The Python Enum class defining the valid values.
        nullable : bool, optional
            If True, allows NULL values. By default False.
        default : Any, optional
            Default value for the column (should be an Enum member or its value).
            By default None.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(sqltypes.Enum(enum_cls), nullable=nullable, default=default)

    def Binary(self, length: int = None, nullable=False) -> Column:
        """
        Defines a SQLAlchemy LargeBinary column.

        Parameters
        ----------
        length : int, optional
            Maximum length of the binary data. By default None.
        nullable : bool, optional
            If True, allows NULL values. By default False.

        Returns
        -------
        sqlalchemy.Column
            The configured Column object.
        """
        return Column(sqltypes.LargeBinary(length=length), nullable=nullable)

    def ForeignKey(
        self,
        target: str,
        dtype: Any = None,
        on_delete: str | None = CASCADE,
        nullable: bool = False,
        use_alter: bool = False,
        on_update: str | None = None,
    ) -> Column:
        """
        Defines a SQLAlchemy Column that acts as a Foreign Key.

        Automatically sets `nullable=True` if `on_delete` is `SET NULL`.

        Parameters
        ----------
        target : str
            The target table and column name (e.g., 'users.id').
        dtype : Any, optional
            The SQLAlchemy type of the foreign key column. Defaults to BigInteger.
            By default None.
        on_delete : str, optional
            The ON DELETE SQL action (e.g., 'CASCADE', 'SET NULL', 'RESTRICT').
            ``None`` writes no clause (NO ACTION), as a schema made by another
            ORM usually has. By default CASCADE.
        nullable : bool, optional
            If True, allows NULL values. Overridden if on_delete='SET NULL'.
            By default False.
        use_alter : bool, optional
            Create the constraint with ``ALTER TABLE`` after both tables exist.
            Set it on one side of a cycle of foreign keys (``app`` -> ``release``
            -> ``app``) so the tables can be sorted without an ``SAWarning``.
            By default False.
        on_update : str, optional
            The ON UPDATE SQL action. By default None (no clause).

        Returns
        -------
        sqlalchemy.Column
            The configured Column object with ForeignKey constraint.
        """
        if on_delete == self.SET_NULL:
            nullable = True
        column_type = dtype if dtype is not None else sqltypes.BigInteger
        if isinstance(column_type, Column):
            column_type = column_type.type
        return Column(
            column_type,
            ForeignKey(target, ondelete=on_delete, onupdate=on_update, use_alter=use_alter),
            nullable=nullable,
        )

    def Relationship(
        self, model: str, back_populates: str = None, post_update: bool = False
    ) -> Any:
        """
        Defines a SQLAlchemy relationship property.

        Sets `passive_deletes=True` to allow the database to handle cascading
        deletes efficiently when used with `ondelete='CASCADE'` in the ForeignKey.

        Parameters
        ----------
        model : str
            The target model class name or string name.
        back_populates : str, optional
            The name of the relationship property on the target model.
            By default None.
        post_update : bool, optional
            Write the foreign key with a separate ``UPDATE`` after the rows
            exist. Needed on one side of a cyclic relationship. By default False.

        Returns
        -------
        sqlalchemy.orm.RelationshipProperty
            The configured relationship object.
        """
        return relationship(
            model,
            back_populates=back_populates,
            passive_deletes=True,
            post_update=post_update,
        )


db = UshkaDB()
