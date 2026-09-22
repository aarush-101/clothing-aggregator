"""SQLAlchemy base and portable column types."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import CHAR, DateTime, String, TypeDecorator, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class GUID(TypeDecorator):
    """UUID column that is native on PostgreSQL and CHAR(36) elsewhere.

    Keeps the schema idiomatic in production while letting the test suite run
    on SQLite without a database server.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value: Any, dialect: Any) -> Optional[str]:
        return None if value is None else str(value)


#: JSONB on PostgreSQL, plain JSON elsewhere.
JSONColumn = JSON().with_variant(postgresql.JSONB(), "postgresql")


def uuid_pk():
    return mapped_column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))


def created_at_column():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def short_string(length: int = 255):
    return String(length)
