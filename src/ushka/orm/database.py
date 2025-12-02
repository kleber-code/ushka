import os
import uuid
import enum
import asyncio
import sqlalchemy.types as sqltypes
from sqlalchemy import Column, ForeignKey, inspect, select, MetaData
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    async_scoped_session,
)
from typing import Optional, List, TypeVar, Type, Any

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


class UshkaDB:
    """
    Asynchronous Database Manager for the Ushka Framework.

    Handles engine creation, session management, and provides the declarative
    Model base with built-in async Active Record methods.
    """

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    RESTRICT = "RESTRICT"

    def __init__(self):
        self.url = os.getenv("USHKA_DB_URL", "sqlite:///ushka.db")

        # Auto-configure driver for Async compatibility
        if "sqlite" in self.url and "aiosqlite" not in self.url:
            self.url = self.url.replace("sqlite://", "sqlite+aiosqlite://")

        self.engine = create_async_engine(self.url, echo=False)

        self.session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # Scoped session linked to the current asyncio task
        self.Session = async_scoped_session(
            self.session_factory, scopefunc=asyncio.current_task
        )

        self.metadata = _Base.metadata
        self.Model = self._create_model_base()

    def _create_model_base(self):
        """Creates the dynamic BaseModel class linked to this DB instance."""
        db = self

        class BaseModel(_Base):
            """
            Base ORM Model with built-in async CRUD operations.
            """

            __abstract__ = True
            id = Column(
                sqltypes.BigInteger, primary_key=True, index=True, autoincrement=True
            )

            # --- INSTANCE METHODS ---

            async def save(self: T) -> T:
                """Persists the current instance to the database."""
                async with db.Session() as session:
                    session.add(self)
                    await session.commit()
                    await session.refresh(self)
                    return self

            async def delete(self) -> None:
                """Removes the current instance from the database."""
                async with db.Session() as session:
                    await session.delete(self)
                    await session.commit()

            def to_dict(self) -> dict:
                """
                Serializes the model to a dictionary.
                This is synchronous as it operates on loaded memory data.
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
            async def create(cls: Type[T], **kwargs) -> T:
                """Creates a new instance and saves it to the database."""
                instance = cls(**kwargs)
                return await instance.save()

            # --- QUERY METHODS ---

            @classmethod
            async def all(cls: Type[T]) -> List[T]:
                """Returns all records for this model."""
                async with db.Session() as session:
                    result = await session.execute(select(cls))
                    return result.scalars().all()

            @classmethod
            async def get(cls: Type[T], id: Any) -> Optional[T]:
                """Retrieves a single record by its Primary Key."""
                async with db.Session() as session:
                    return await session.get(cls, id)

            @classmethod
            async def first(cls: Type[T], **kwargs) -> Optional[T]:
                """Returns the first record matching the filters."""
                async with db.Session() as session:
                    stmt = select(cls).filter_by(**kwargs)
                    result = await session.execute(stmt)
                    return result.scalars().first()

            @classmethod
            async def filter(cls: Type[T], **kwargs) -> List[T]:
                """
                Returns a list of records matching the filters.
                """
                async with db.Session() as session:
                    stmt = select(cls).filter_by(**kwargs)
                    result = await session.execute(stmt)
                    return result.scalars().all()

            # --- SQLALCHEMY 2.0 HELPERS ---

            @classmethod
            def select(cls):
                """
                Returns a raw SQLAlchemy Select statement.
                Usage: await db.execute(User.select().where(...))
                """
                return select(cls)

            def __repr__(self):
                pk = getattr(self, "id", "No-ID")
                return f"<{self.__class__.__name__} {pk}>"

        return BaseModel

    # --- EXECUTION HELPERS ---

    async def execute(self, stmt):
        """Executes a raw SQL statement or SQLAlchemy construct."""
        async with self.Session() as session:
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
        type_engine = sqltypes.String(length)
        if choices:
            type_engine = sqltypes.Enum(
                *choices, name=None, native_enum=False, length=length
            )
        return Column(type_engine, unique=unique, nullable=nullable, default=default)

    def UUID(
        self, unique=False, nullable=False, primary_key=False, default=None
    ) -> Column:
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
        return Column(sqltypes.Text, nullable=nullable, default=default)

    def Int(self, unique=False, nullable=False, default=None) -> Column:
        return Column(
            sqltypes.Integer, unique=unique, nullable=nullable, default=default
        )

    def BigInt(self, unique=False, nullable=False, default=None) -> Column:
        return Column(
            sqltypes.BigInteger, unique=unique, nullable=nullable, default=default
        )

    def Float(self, nullable=False, default=0.0) -> Column:
        return Column(sqltypes.Float, nullable=nullable, default=default)

    def Decimal(self, precision=10, scale=2, nullable=False, default=0) -> Column:
        return Column(
            sqltypes.Numeric(precision, scale), nullable=nullable, default=default
        )

    def Bool(self, default=False, nullable=False) -> Column:
        return Column(sqltypes.Boolean, nullable=nullable, default=default)

    def DateTime(self, auto_now=False, nullable=False) -> Column:
        return Column(sqltypes.DateTime, nullable=nullable, default=func.now() if auto_now else None)

    def Date(self, auto_now=False, nullable=False) -> Column:
        return Column(sqltypes.Date, nullable=nullable, default=func.now() if auto_now else None)

    def Time(self, nullable=False) -> Column:
        return Column(sqltypes.Time, nullable=nullable)

    def JSON(self, nullable=False, default=None) -> Column:
        default_val = default if default is not None else {}
        return Column(sqltypes.JSON, nullable=nullable, default=default_val)

    def Enum(self, enum_cls: Type[enum.Enum], nullable=False, default=None) -> Column:
        return Column(sqltypes.Enum(enum_cls), nullable=nullable, default=default)

    def Binary(self, length: int = None, nullable=False) -> Column:
        return Column(sqltypes.LargeBinary(length=length), nullable=nullable)

    def ForeignKey(
        self,
        target: str,
        dtype: Any = None,
        on_delete: str = CASCADE,
        nullable: bool = False,
    ) -> Column:
        if on_delete == self.SET_NULL:
            nullable = True
        column_type = dtype if dtype is not None else sqltypes.BigInteger
        if isinstance(column_type, Column):
            column_type = column_type.type
        return Column(
            column_type, ForeignKey(target, ondelete=on_delete), nullable=nullable
        )

    def Relationship(self, model: str, back_populates: str = None) -> Any:
        return relationship(model, back_populates=back_populates, passive_deletes=True)


db = UshkaDB()
