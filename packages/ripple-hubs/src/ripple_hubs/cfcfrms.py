"""A simulated CFCFRMS hub (MHA/I4C), following the SOP for NCRP-CFCFRMS (January 2026).

A police officer pushes a complaint (SOP 6.1 f). The hub sends a notice to the bank that received the victim's
payment (6.1 g). Each bank answers with what it held and where the rest went, and the hub sends a notice for every
onward hop to the bank that received it, "till the complete money trail is established" (6.1 g, j). Money that
reached an institution not on the network is recorded as off-network, and exits carry their identifiers.

Every rupee reported is accounted for at all times: held, cashed out, off-network, not found, or still waiting
for an answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Integer, String, Text, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from ripple_core.clock import Clock
from ripple_core.messages import AccountRef, Complaint, Exit, Notice, NoticeResponse, Payment
from ripple_core.network import Network
from ripple_service.config import load_keyring, load_service_config, load_signing_key
from ripple_service.db import SqlReplayGuard, UtcDateTime, append_audit, init_db, make_engine, transaction
from ripple_service.transport import Courier, Envelopes, Sealed, mtls_post

log = logging.getLogger(__name__)

FILERS = frozenset({"web", "sim"})  # parties allowed to push complaints and read trails
MAX_NOTICES_PER_CASE = 500


class HubBase(DeclarativeBase):
    pass


class CaseRow(HubBase):
    __tablename__ = "cases"

    ack_number: Mapped[str] = mapped_column(String(14), primary_key=True)
    complaint: Mapped[str] = mapped_column(Text)
    filed_at: Mapped[datetime] = mapped_column(UtcDateTime())


class NoticeOut(HubBase):
    __tablename__ = "notices"

    notice_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    ack_number: Mapped[str] = mapped_column(String(14), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(String(32))
    to_member: Mapped[str | None] = mapped_column(String(32))  # None: the account is not on the network
    notice: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class TrailAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    notice_id: str
    parent_id: str | None
    layer: int
    member: str | None
    account: AccountRef
    credit: Payment
    traced_in: int
    state: Literal["answered", "not_found", "off_network", "waiting"]
    held: int = 0
    lien_id: str | None = None
    exits: tuple[Exit, ...] = ()
    reason: str | None = None


class Trail(BaseModel):
    model_config = ConfigDict(frozen=True)

    ack_number: str
    reported: int
    held: int
    cashed_out: int
    off_network: int
    not_found: int
    waiting: int
    complete: bool
    accounts: tuple[TrailAccount, ...]


class TrailQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ack_number: str


@dataclass
class Tracer:
    factory: sessionmaker[Session]
    courier: Courier
    network: Network
    clock: Clock

    def open_case(self, complaint: Complaint) -> bool:
        """Record a complaint and its first notice; False if the case already exists."""
        with transaction(self.factory) as session:
            if session.get(CaseRow, complaint.ack_number) is not None:
                return False
            now = self.clock.now()
            session.add(
                CaseRow(ack_number=complaint.ack_number, complaint=complaint.model_dump_json(), filed_at=now)
            )
            self._add_notice(
                session,
                complaint.ack_number,
                parent_id=None,
                layer=1,
                credit=complaint.payment,
                beneficiary=complaint.beneficiary,
                traced=complaint.payment.amount,
            )
            append_audit(session, now, "cfcfrms", "case_opened", {"ack_number": complaint.ack_number})
            return True

    def run(self, ack_number: str) -> None:
        """Send every notice still unanswered for a case, following onward hops until the trail is complete."""
        while True:
            with transaction(self.factory) as session:
                pending = session.scalars(
                    select(NoticeOut)
                    .where(
                        NoticeOut.ack_number == ack_number,
                        NoticeOut.to_member.is_not(None),
                        NoticeOut.response.is_(None),
                        NoticeOut.error.is_(None),
                    )
                    .order_by(NoticeOut.seq)
                ).all()
            if not pending:
                return
            for row in pending:
                self._deliver(row)

    def _deliver(self, row: NoticeOut) -> None:
        notice = Notice.model_validate_json(row.notice)
        assert row.to_member is not None  # noqa: S101 - only network members are delivered to
        sent_at = self.clock.now()
        try:
            response = self._ask(row.to_member, notice)
        except (ConnectionError, OSError, ValueError, ValidationError) as exc:
            log.warning("notice %s to %s failed: %s", notice.notice_id, row.to_member, exc)
            with transaction(self.factory) as session:
                stored = session.get(NoticeOut, row.notice_id)
                if stored is not None:
                    stored.error, stored.sent_at = str(exc)[:500], sent_at
            return
        with transaction(self.factory) as session:
            stored = session.get(NoticeOut, row.notice_id)
            if stored is None or stored.response is not None:
                return
            stored.response, stored.sent_at, stored.answered_at = (
                response.model_dump_json(),
                sent_at,
                self.clock.now(),
            )
            for hop in response.onward:
                self._add_notice(
                    session,
                    notice.ack_number,
                    parent_id=notice.notice_id,
                    layer=notice.layer + 1,
                    credit=hop.payment,
                    beneficiary=hop.to,
                    traced=hop.traced_amount,
                )
            append_audit(
                session,
                self.clock.now(),
                "cfcfrms",
                "notice_answered",
                {"notice_id": notice.notice_id, "member": row.to_member, "held": response.held_amount},
            )

    def _ask(self, member: str, notice: Notice) -> NoticeResponse:
        opened = self.courier.call(member, "/v1/notices", notice, idempotency_key=notice.notice_id)
        response = NoticeResponse.model_validate(opened.payload)
        if response.notice_id != notice.notice_id:
            raise ValueError("the bank answered a different notice")
        return response

    def _add_notice(
        self,
        session: Session,
        ack: str,
        *,
        parent_id: str | None,
        layer: int,
        credit: Payment,
        beneficiary: AccountRef,
        traced: int,
    ) -> None:
        count = session.scalar(select(func.count()).where(NoticeOut.ack_number == ack)) or 0
        if count >= MAX_NOTICES_PER_CASE:
            raise RuntimeError(f"case {ack} has more than {MAX_NOTICES_PER_CASE} notices")
        holder = self.network.holder_of(beneficiary)
        notice = Notice(
            notice_id=f"{ack}-{count + 1:03d}",
            ack_number=ack,
            layer=layer,
            credit=credit,
            beneficiary=beneficiary,
            traced_amount=traced,
            issued_at=self.clock.now(),
        )
        session.add(
            NoticeOut(
                notice_id=notice.notice_id,
                ack_number=ack,
                seq=count + 1,
                parent_id=parent_id,
                to_member=holder.id if holder is not None and holder.kind != "hub" else None,
                notice=notice.model_dump_json(),
                response=None,
                error=None,
                sent_at=None,
                answered_at=None,
            )
        )

    def trail(self, ack_number: str) -> Trail | None:
        with self.factory() as session:
            case = session.get(CaseRow, ack_number)
            if case is None:
                return None
            rows = session.scalars(
                select(NoticeOut).where(NoticeOut.ack_number == ack_number).order_by(NoticeOut.seq)
            ).all()
        accounts = tuple(_trail_account(r) for r in rows)
        totals = dict.fromkeys(("held", "cashed_out", "off_network", "not_found", "waiting"), 0)
        for a in accounts:
            totals["held"] += a.held
            totals["cashed_out"] += sum(e.traced_amount for e in a.exits)
            if a.state != "answered":
                totals[a.state] += a.traced_in
        reported = Complaint.model_validate_json(case.complaint).payment.amount
        return Trail(
            ack_number=ack_number,
            reported=reported,
            complete=totals["waiting"] == 0,
            accounts=accounts,
            **totals,
        )


def _trail_account(row: NoticeOut) -> TrailAccount:
    notice = Notice.model_validate_json(row.notice)
    base = {
        "notice_id": row.notice_id,
        "parent_id": row.parent_id,
        "layer": notice.layer,
        "member": row.to_member,
        "account": notice.beneficiary,
        "credit": notice.credit,
        "traced_in": notice.traced_amount,
    }
    if row.to_member is None:
        return TrailAccount(**base, state="off_network")
    if row.response is None:
        return TrailAccount(**base, state="waiting", reason=row.error)
    response = NoticeResponse.model_validate_json(row.response)
    if response.status == "not_found":
        return TrailAccount(**base, state="not_found", reason=response.reason)
    return TrailAccount(
        **base, state="answered", held=response.held_amount, lien_id=response.lien_id, exits=response.exits
    )


def build_app(tracer: Tracer, envelopes: Envelopes) -> FastAPI:
    app = FastAPI(title="Simulated CFCFRMS hub", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"member": "cfcfrms", "status": "ok", "now": tracer.clock.now().isoformat()}

    @app.post("/v1/complaints")
    def push_complaint(body: Sealed, background: BackgroundTasks) -> Sealed:
        opened = envelopes.open(body, FILERS)
        try:
            complaint = Complaint.model_validate(opened.payload)
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not a valid complaint") from exc
        created = tracer.open_case(complaint)
        background.add_task(tracer.run, complaint.ack_number)
        return envelopes.seal({"ack_number": complaint.ack_number, "created": created}, opened.sender)

    @app.post("/v1/trails")
    def read_trail(body: Sealed) -> Sealed:
        opened = envelopes.open(body, FILERS)
        try:
            query = TrailQuery.model_validate(opened.payload)
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not a valid query") from exc
        trail = tracer.trail(query.ack_number)
        if trail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such case")
        return envelopes.seal(trail, opened.sender)

    return app


def create_app() -> FastAPI:
    """The app `ripple up` starts, configured from the environment and `.ripple/`."""
    config = load_service_config("cfcfrms")
    factory = init_db(make_engine(config.paths.database("cfcfrms")), HubBase.metadata)
    envelopes = Envelopes(
        load_signing_key(config.paths, "cfcfrms"),
        load_keyring(config.paths),
        config.clock,
        SqlReplayGuard(factory),
    )
    courier = Courier(envelopes, mtls_post(config.network, config.paths, "cfcfrms"))
    return build_app(Tracer(factory, courier, config.network, config.clock), envelopes)
