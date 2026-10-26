from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DatabaseError

from ripple_core.clock import IST
from ripple_service.db import (
    AuditEntry,
    SqlReplayGuard,
    append_audit,
    init_db,
    make_engine,
    transaction,
    verify_audit,
)

T0 = datetime(2026, 10, 25, 21, 0, tzinfo=IST)


def test_audit_log_is_chained_and_append_only() -> None:
    factory = init_db(make_engine(None))
    with transaction(factory) as s:
        first = append_audit(s, T0, "bank-b", "lien_placed", {"amount": 100})
        second = append_audit(s, T0 + timedelta(minutes=1), "bank-b", "lien_released", {"amount": 100})
        assert second.prev_hash == first.hash
        assert verify_audit(s) is None
        assert first.at == T0.astimezone(UTC)

    with pytest.raises(DatabaseError, match="append-only"), transaction(factory) as s:
        s.execute(update(AuditEntry).where(AuditEntry.seq == 1).values(record='{"amount":1}'))
    with pytest.raises(DatabaseError, match="append-only"), transaction(factory) as s:
        s.execute(text("DELETE FROM audit_log"))


def test_audit_verification_finds_a_tampered_row() -> None:
    factory = init_db(make_engine(None))
    with transaction(factory) as s:
        append_audit(s, T0, "bank-b", "a", {"n": 1})
        append_audit(s, T0, "bank-b", "b", {"n": 2})
        s.execute(text("DROP TRIGGER audit_no_update"))  # what someone editing the file directly could do
        s.execute(text("UPDATE audit_log SET record = :record WHERE seq = 2").bindparams(record='{"n":3}'))
        assert verify_audit(s) == 2


def test_replay_guard_remembers_nonces_per_sender() -> None:
    guard = SqlReplayGuard(init_db(make_engine(None)))
    until = T0 + timedelta(minutes=2)
    assert guard.remember("bank-b", "n1", until)
    assert not guard.remember("bank-b", "n1", until)
    assert guard.remember("bank-c", "n1", until)


def test_naive_times_are_refused() -> None:
    factory = init_db(make_engine(None))
    with pytest.raises(Exception, match="timezone-aware"), transaction(factory) as s:
        append_audit(s, datetime(2026, 1, 1), "x", "y", {})  # noqa: DTZ001 - checking refusal
