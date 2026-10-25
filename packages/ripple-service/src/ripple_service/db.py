"""Each service's own SQLite database, its replay store, and its tamper-evident audit log.

The audit log is append-only: SQLite triggers refuse any update or delete, and each row carries the SHA-256 of the
previous row's hash and its own content, so editing the file directly breaks the chain and `verify_audit` says where.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    Dialect,
    Engine,
    Integer,
    MetaData,
    String,
    Text,
    TypeDecorator,
    create_engine,
    event,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

GENESIS = "0" * 64


class Base(DeclarativeBase):
    """Tables every service has: the replay store and the audit log. Each service declares its own tables on its
    own base, so no service's database contains another's tables."""


class UtcDateTime(TypeDecorator[datetime]):
    """SQLite stores no time zone, so store UTC and hand back aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else _to_utc(value)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("times must be timezone-aware")
    return value.astimezone(UTC).replace(tzinfo=None)


class Nonce(Base):
    __tablename__ = "nonces"

    sender: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    until: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)


class AuditEntry(Base):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime())
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    record: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


_AUDIT_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END",
)


def make_engine(path: Path | None) -> Engine:
    """An engine for the service's database file, or an in-memory database for tests when `path` is None."""
    if path is None:
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def init_db(engine: Engine, *service_tables: MetaData) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    for metadata in service_tables:
        metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _AUDIT_TRIGGERS:
            conn.execute(text(ddl))
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session, session.begin():
        yield session


class SqlReplayGuard:
    """Nonces seen within the freshness window, stored in the service's own database."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def remember(self, sender: str, nonce: str, until: datetime) -> bool:
        with transaction(self._factory) as session:
            if session.get(Nonce, (sender, nonce)) is not None:
                return False
            session.add(Nonce(sender=sender, nonce=nonce, until=until))
            return True


def _entry_hash(prev_hash: str, at: datetime, actor: str, action: str, record: str) -> str:
    material = json.dumps([prev_hash, _to_utc(at).isoformat(), actor, action, record], separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append_audit(
    session: Session, at: datetime, actor: str, action: str, record: dict[str, Any]
) -> AuditEntry:
    last = session.scalars(select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(1)).first()
    prev_hash = last.hash if last else GENESIS
    body = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    entry = AuditEntry(
        at=at,
        actor=actor,
        action=action,
        record=body,
        prev_hash=prev_hash,
        hash=_entry_hash(prev_hash, at, actor, action, body),
    )
    session.add(entry)
    session.flush()
    return entry


def verify_audit(session: Session) -> int | None:
    """Walk the chain; return the sequence number of the first broken row, or None if it is intact."""
    prev = GENESIS
    for entry in session.scalars(select(AuditEntry).order_by(AuditEntry.seq)):
        expected = _entry_hash(prev, entry.at, entry.actor, entry.action, entry.record)
        if entry.prev_hash != prev or entry.hash != expected:
            return entry.seq
        prev = entry.hash
    return None
