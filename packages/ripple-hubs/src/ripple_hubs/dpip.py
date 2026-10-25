"""The simulated DPIP: the payee risk lookup banks call before money leaves (PRD P1 and P3).

Two sources feed it, both as keyed hashes so no raw account data is stored or exchanged:

- the suspect registry: accounts on a CFCFRMS trail that received reported money and passed it on or cashed it out
  (an account that only received money, such as a shop paid for goods, is not on it);
- risk signals banks publish when they put a suspected mule on a temporary debit hold, with a level and an expiry.

The answer is the highest level found, with one plain reason per match. Runs inside the hub's process.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from ripple_core.clock import IST, Clock
from ripple_core.dpip import identifier_hashes
from ripple_core.messages import RiskLevel, RiskSignal
from ripple_service.db import UtcDateTime, append_audit, transaction

LEVELS = {"none": 0, "medium": 1, "high": 2, "very_high": 3}
REASONS = {
    "temporary_debit_hold": "a temporary debit hold on a suspected mule credit",
    "confirmed_mule": "a confirmed money mule",
}


class DpipBase(DeclarativeBase):
    pass


class SignalRow(DpipBase):
    __tablename__ = "dpip_signals"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identifier_hash: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str] = mapped_column(String(40))
    publisher: Mapped[str] = mapped_column(String(32))
    published_at: Mapped[datetime] = mapped_column(UtcDateTime())
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CheckQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier_hashes: tuple[str, ...] = Field(min_length=1, max_length=8)


class CheckAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Suspect:
    ack_number: str
    layer: int


@dataclass
class Dpip:
    factory: sessionmaker[Session]
    key: bytes
    clock: Clock

    def publish(self, signal: RiskSignal, publisher: str) -> int:
        now = self.clock.now()
        with transaction(self.factory) as session:
            for h in signal.identifier_hashes:
                session.add(SignalRow(identifier_hash=h, level=signal.level.value, reason_code=signal.reason_code,
                                      publisher=publisher, published_at=now, expires_at=signal.expires_at))  # fmt: skip
            append_audit(session, now, publisher, "dpip.signal",
                         {"hashes": len(signal.identifier_hashes), "level": signal.level.value,
                          "reason_code": signal.reason_code})  # fmt: skip
        return len(signal.identifier_hashes)

    def check(self, hashes: tuple[str, ...], registry: dict[str, Suspect]) -> CheckAnswer:
        now = self.clock.now()
        level = 0
        reasons: list[str] = []
        for h in hashes:
            suspect = registry.get(h)
            if suspect is not None:
                level = LEVELS[RiskLevel.VERY_HIGH.value]
                reasons.append(
                    f"On the suspect registry: it received reported money at layer {suspect.layer} of CFCFRMS "
                    f"complaint {suspect.ack_number} and passed it on or cashed it out."
                )
        with self.factory() as session:
            rows = session.query(SignalRow).filter(
                SignalRow.identifier_hash.in_(hashes), SignalRow.expires_at > now
            )
            for row in rows:
                level = max(level, LEVELS[row.level])
                when = row.published_at.astimezone(IST).strftime("%d %b %Y")
                reasons.append(
                    f"A member bank reported it on {when} for {REASONS.get(row.reason_code, row.reason_code)}."
                )
        name = next(k for k, v in LEVELS.items() if v == level)
        return CheckAnswer(level=name, reasons=tuple(dict.fromkeys(reasons)))


def registry_from(trails: Iterable[Any], key: bytes) -> dict[str, Suspect]:
    """Hash every account on the trails that passed reported money on or cashed it out."""
    registry: dict[str, Suspect] = {}
    for trail in trails:
        accounts = trail.accounts
        parents = {a.parent_id for a in accounts if a.parent_id}
        for a in accounts:
            if a.state != "answered" or not (a.notice_id in parents or a.exits):
                continue
            for h in identifier_hashes(key, a.account):
                registry.setdefault(h, Suspect(trail.ack_number, a.layer))
    return registry
