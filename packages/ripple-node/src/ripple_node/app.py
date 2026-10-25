"""The bank node's HTTP service.

Routes take and return signed envelopes. Only the simulator ("sim") may open accounts and post transactions,
standing in for the core banking feed, and only the CFCFRMS hub may send notices. Only the web gateway ("web") may
call the officer routes; the gateway checks the officer's role and bank and passes the officer's ID as `actor`.
The notice views are read-only. The FRM routes run mule cases and RBI's temporary debit holds, and every change
they make goes to the audit log.

Each new batch of postings, and each notice, reruns the red-flag rules on the accounts it touches.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ripple_core.clock import Clock
from ripple_core.messages import AccountOpening, AccountRef, LedgerPosting, Notice
from ripple_core.signing import Opened
from ripple_core.tracing import LedgerError
from ripple_node import detection, holds, ledger, monitoring, officer, payments, responder
from ripple_node.detection import Thresholds
from ripple_service.config import load_keyring, load_service_config, load_signing_key
from ripple_service.db import AuditEntry, SqlReplayGuard, init_db, make_engine, transaction, verify_audit
from ripple_service.transport import Envelopes, Sealed

SIMULATOR = "sim"
HUB = "cfcfrms"
GATEWAY = "web"


class NoticeQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    notice_id: str


class PostingBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    postings: tuple[LedgerPosting, ...]


class Request(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


Text = Annotated[str, Field(max_length=2000)]
Actor = Annotated[str, Field(min_length=1, max_length=64)]


class CasesQuery(Request):
    include_closed: bool = False


class Dismissal(Request):
    actor: Actor
    account_number: str
    reason: Annotated[str, Field(min_length=10, max_length=2000)]


class Placement(Request):
    actor: Actor
    account_number: str
    flag_keys: Annotated[tuple[str, ...], Field(min_length=1, max_length=50)]
    contact: Annotated[str, Field(min_length=5, max_length=200)]
    whole_account: bool = False
    account_level_reason: Text | None = None


class HoldStep(Request):
    actor: Actor
    hold_id: Annotated[str, Field(pattern=r"^H[0-9A-F]{16}$")]


class Explanation(HoldStep):
    summary: Text


class Decision(HoldStep):
    decision: Literal["release", "report"]
    reason: Text


class Instruction(HoldStep):
    instruction: Literal["release", "continue"]
    authority: Annotated[str, Field(min_length=3, max_length=200)]


class Confirmation(HoldStep):
    grounds: Text


class StrFiled(HoldStep):
    reference: Annotated[str, Field(min_length=3, max_length=64)]


class ShadowRun(Request):
    budget_per_day: Annotated[float, Field(gt=0, le=10_000)]


class Approval(Request):
    actor: Actor
    budget_per_day: Annotated[float, Field(gt=0, le=10_000)] | None = None
    pass_through_minutes: Annotated[int, Field(ge=1, le=10_080)]
    new_senders: Annotated[int, Field(ge=2, le=1_000)]
    profile_multiple: Annotated[float, Field(gt=0, le=1_000)]
    dormant_days: Annotated[int, Field(ge=1, le=3_650)]
    cash_out_minutes: Annotated[int, Field(ge=1, le=10_080)]


class AccountQuery(Request):
    account_number: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]


class LienRelease(Request):
    actor: Actor
    lien_id: Annotated[str, Field(min_length=4, max_length=32)]
    authority: Annotated[str, Field(min_length=3, max_length=200)]
    order: Annotated[str, Field(min_length=3, max_length=64)]
    reason: Text
    to_victim: bool = False


class HoldNote(HoldStep):
    note: Annotated[str, Field(min_length=1, max_length=2000)]


class AuditQuery(Request):
    limit: Annotated[int, Field(ge=1, le=1000)] = 200


class PaymentCheck(Request):
    sender_account: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]
    payee: AccountRef
    amount: Annotated[int, Field(gt=0, le=10**13)]
    dpip_level: Literal["none", "medium", "high", "very_high"] = "none"
    dpip_reasons: Annotated[tuple[Annotated[str, Field(max_length=400)], ...], Field(max_length=10)] = ()


@dataclass(frozen=True)
class NodeContext:
    member_id: str
    factory: sessionmaker[Session]
    envelopes: Envelopes
    clock: Clock
    name: str = ""
    bank_code: str = ""


def build_app(ctx: NodeContext) -> FastAPI:  # noqa: PLR0915 - one short function per route
    app = FastAPI(title=f"Ripple bank node: {ctx.member_id}", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"member": ctx.member_id, "status": "ok", "now": ctx.clock.now().isoformat()}

    @app.post("/v1/accounts")
    def open_account(body: Sealed) -> Sealed:
        opened = ctx.envelopes.open(body, {SIMULATOR})
        opening = _parse(AccountOpening, opened)
        with transaction(ctx.factory) as session:
            try:
                ledger.open_account(session, opening)
            except ledger.LedgerConflict as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return ctx.envelopes.seal({"opened": opening.account_number}, opened.sender)

    @app.post("/v1/postings")
    def post_transactions(body: Sealed) -> Sealed:
        """Post a batch of transactions all or nothing, in order."""
        opened = ctx.envelopes.open(body, {SIMULATOR})
        batch = _parse(PostingBatch, opened)
        with transaction(ctx.factory) as session:
            for i, posting in enumerate(batch.postings):
                try:
                    ledger.post(session, posting)
                except ledger.LedgerConflict as exc:
                    raise HTTPException(status.HTTP_409_CONFLICT, f"posting {i}: {exc}") from exc
            monitoring.rescan(session, {p.account_number for p in batch.postings}, ctx.clock.now())
        return ctx.envelopes.seal({"posted": len(batch.postings)}, opened.sender)

    @app.post("/v1/notices")
    def answer_notice(body: Sealed) -> Sealed:
        opened = ctx.envelopes.open(body, {HUB})
        notice = _parse(Notice, opened)
        with transaction(ctx.factory) as session:
            try:
                response = responder.respond(session, notice, ctx.clock.now(), opened.sender)
            except LedgerError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, f"ledger does not add up: {exc}") from exc
            if response.status == "matched":  # its counterparties here are now linked to a reported account
                monitoring.rescan(
                    session, session.scalars(select(ledger.Account.account_number)), ctx.clock.now()
                )
        return ctx.envelopes.seal(response, opened.sender, opened.idempotency_key)

    @app.post("/v1/officer/notices")
    def officer_notices(body: Sealed) -> Sealed:
        opened = ctx.envelopes.open(body, {GATEWAY})
        with ctx.factory() as session:
            rows = officer.notices(session)
        return ctx.envelopes.seal({"notices": [r.model_dump(mode="json") for r in rows]}, opened.sender)

    @app.post("/v1/officer/notice")
    def officer_notice(body: Sealed) -> Sealed:
        opened = ctx.envelopes.open(body, {GATEWAY})
        query = _parse(NoticeQuery, opened)
        with ctx.factory() as session:
            detail = officer.notice_detail(session, query.notice_id, ctx.clock.now())
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such notice at this bank")
        return ctx.envelopes.seal(detail, opened.sender)

    @app.post("/v1/officer/liens")
    def officer_liens(body: Sealed) -> Sealed:
        opened = ctx.envelopes.open(body, {GATEWAY})
        with ctx.factory() as session:
            rows = officer.liens(session)
        return ctx.envelopes.seal({"liens": [r.model_dump(mode="json") for r in rows]}, opened.sender)

    def frm[M: BaseModel](body: Sealed, model: type[M], act: Callable[[Session, M], Any]) -> Sealed:
        """Run one FRM step in a transaction; a step the SOP does not allow comes back as 409 with the reason."""
        opened = ctx.envelopes.open(body, {GATEWAY})
        request = _parse(model, opened)
        with transaction(ctx.factory) as session:
            try:
                result = act(session, request)
            except ledger.LedgerConflict as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return ctx.envelopes.seal(result, opened.sender)

    def hold_view(session: Session, row: ledger.HoldRow) -> dict[str, Any]:
        """The hold, with the account's identifiers so the bank's gateway can publish a DPIP signal."""
        view = holds.view(session, row, ctx.clock.now()).model_dump(mode="json")
        account = session.get(ledger.Account, row.account_number)
        if account is not None:
            view["account_ref"] = {
                "ifsc": account.ifsc,
                "account_number": account.account_number,
                "vpa": account.vpa,
            }
        return view

    @app.post("/v1/officer/cases")
    def mule_cases(body: Sealed) -> Sealed:
        def act(session: Session, q: CasesQuery) -> dict[str, Any]:
            rows = monitoring.cases(session, ctx.clock.now(), include_closed=q.include_closed)
            return {"cases": [c.model_dump(mode="json") for c in rows]}

        return frm(body, CasesQuery, act)

    @app.post("/v1/officer/cases/dismiss")
    def dismiss_case(body: Sealed) -> Sealed:
        def act(session: Session, q: Dismissal) -> dict[str, Any]:
            closed = monitoring.dismiss(session, q.account_number, actor=q.actor, reason=q.reason,
                                        now=ctx.clock.now())  # fmt: skip
            if not closed:
                raise ledger.LedgerConflict("this account has no open flags")
            return {"dismissed": closed}

        return frm(body, Dismissal, act)

    @app.post("/v1/officer/holds")
    def hold_queue(body: Sealed) -> Sealed:
        def act(session: Session, _q: CasesQuery) -> dict[str, Any]:
            return {"holds": [h.model_dump(mode="json") for h in holds.holds(session, ctx.clock.now())]}

        return frm(body, CasesQuery, act)

    @app.post("/v1/officer/holds/place")
    def place_hold(body: Sealed) -> Sealed:
        def act(session: Session, q: Placement) -> dict[str, Any]:
            row = holds.place(
                session, now=ctx.clock.now(), actor=q.actor, bank_name=ctx.name or ctx.member_id,
                account_number=q.account_number, flag_keys=q.flag_keys, contact=q.contact,
                whole_account=q.whole_account, account_level_reason=q.account_level_reason,
            )  # fmt: skip
            return hold_view(session, row)

        return frm(body, Placement, act)

    @app.post("/v1/officer/holds/explanation")
    def hold_explanation(body: Sealed) -> Sealed:
        def act(session: Session, q: Explanation) -> dict[str, Any]:
            row = holds.record_explanation(
                session, q.hold_id, now=ctx.clock.now(), actor=q.actor, summary=q.summary
            )
            return hold_view(session, row)

        return frm(body, Explanation, act)

    @app.post("/v1/officer/holds/decision")
    def hold_decision(body: Sealed) -> Sealed:
        def act(session: Session, q: Decision) -> dict[str, Any]:
            row = holds.decide(session, q.hold_id, now=ctx.clock.now(), actor=q.actor, decision=q.decision,
                               reason=q.reason)  # fmt: skip
            return hold_view(session, row)

        return frm(body, Decision, act)

    @app.post("/v1/officer/holds/instruction")
    def hold_instruction(body: Sealed) -> Sealed:
        def act(session: Session, q: Instruction) -> dict[str, Any]:
            row = holds.record_instruction(session, q.hold_id, now=ctx.clock.now(), actor=q.actor,
                                           instruction=q.instruction, authority=q.authority)  # fmt: skip
            return hold_view(session, row)

        return frm(body, Instruction, act)

    @app.post("/v1/officer/holds/confirm-mule")
    def hold_confirm(body: Sealed) -> Sealed:
        def act(session: Session, q: Confirmation) -> dict[str, Any]:
            row = holds.confirm_mule(session, q.hold_id, now=ctx.clock.now(), actor=q.actor, grounds=q.grounds,
                                     bank_name=ctx.name or ctx.member_id, bank_code=ctx.bank_code)  # fmt: skip
            return hold_view(session, row)

        return frm(body, Confirmation, act)

    @app.post("/v1/officer/holds/str-filed")
    def hold_str_filed(body: Sealed) -> Sealed:
        def act(session: Session, q: StrFiled) -> dict[str, Any]:
            row = holds.record_str_filed(session, q.hold_id, now=ctx.clock.now(), actor=q.actor,
                                         reference=q.reference)  # fmt: skip
            return hold_view(session, row)

        return frm(body, StrFiled, act)

    @app.post("/v1/officer/detection/thresholds")
    def thresholds(body: Sealed) -> Sealed:
        def act(session: Session, _q: CasesQuery) -> dict[str, Any]:
            return asdict(monitoring.current_thresholds(session))

        return frm(body, CasesQuery, act)

    @app.post("/v1/officer/detection/shadow-run")
    def shadow_run(body: Sealed) -> Sealed:
        def act(session: Session, q: ShadowRun) -> dict[str, Any]:
            return calibration_json(monitoring.shadow_run(session, ctx.clock.now(), q.budget_per_day))

        return frm(body, ShadowRun, act)

    @app.post("/v1/officer/detection/approve")
    def approve(body: Sealed) -> Sealed:
        def act(session: Session, q: Approval) -> dict[str, Any]:
            settings = Thresholds(
                pass_through_minutes=q.pass_through_minutes, new_senders=q.new_senders,
                profile_multiple=q.profile_multiple, dormant_days=q.dormant_days,
                cash_out_minutes=q.cash_out_minutes,
            )  # fmt: skip
            monitoring.approve_thresholds(session, settings, actor=q.actor, now=ctx.clock.now(),
                                          budget_per_day=q.budget_per_day)  # fmt: skip
            return asdict(settings)

        return frm(body, Approval, act)

    @app.post("/v1/officer/account")
    def account(body: Sealed) -> Sealed:
        opened = ctx.envelopes.open(body, {GATEWAY})
        query = _parse(AccountQuery, opened)
        with ctx.factory() as session:
            found = officer.account_view(session, query.account_number, ctx.clock.now())
            cases = [c for c in monitoring.cases(session, ctx.clock.now(), include_closed=True)
                     if c.account_number == query.account_number]  # fmt: skip
            account_holds = [
                h for h in holds.holds(session, ctx.clock.now()) if h.account_number == query.account_number
            ]
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such account at this bank")
        view = found.model_dump(mode="json")
        view["flags"] = [c.model_dump(mode="json") for c in cases]
        view["holds"] = [h.model_dump(mode="json") for h in account_holds]
        return ctx.envelopes.seal(view, opened.sender)

    @app.post("/v1/officer/liens/release")
    def release_lien(body: Sealed) -> Sealed:
        def act(session: Session, q: LienRelease) -> dict[str, Any]:
            row = officer.release_lien(session, q.lien_id, now=ctx.clock.now(), actor=q.actor, authority=q.authority,
                                       order=q.order, reason=q.reason, to_victim=q.to_victim)  # fmt: skip
            return {"lien_id": row.lien_id, "released_at": ctx.clock.now().isoformat(), "amount": row.amount}

        return frm(body, LienRelease, act)

    @app.post("/v1/officer/holds/note")
    def hold_note(body: Sealed) -> Sealed:
        def act(session: Session, q: HoldNote) -> dict[str, Any]:
            return hold_view(
                session, holds.add_note(session, q.hold_id, now=ctx.clock.now(), actor=q.actor, note=q.note)
            )

        return frm(body, HoldNote, act)

    @app.post("/v1/officer/detection/history")
    def threshold_history(body: Sealed) -> Sealed:
        def act(session: Session, _q: CasesQuery) -> dict[str, Any]:
            return {"history": monitoring.threshold_history(session)}

        return frm(body, CasesQuery, act)

    @app.post("/v1/officer/audit")
    def audit(body: Sealed) -> Sealed:
        """The newest audit entries, and whether the hash chain is intact from the first row."""

        def act(session: Session, q: AuditQuery) -> dict[str, Any]:
            rows = session.scalars(select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(q.limit))
            entries = [
                {"seq": r.seq, "at": r.at.isoformat(), "actor": r.actor, "action": r.action,
                 "record": json.loads(r.record), "hash": r.hash}
                for r in rows
            ]  # fmt: skip
            return {"entries": entries, "broken_at": verify_audit(session)}

        return frm(body, AuditQuery, act)

    @app.post("/v1/officer/payment-check")
    def payment_check(body: Sealed) -> Sealed:
        def act(session: Session, q: PaymentCheck) -> dict[str, Any]:
            result = payments.check(
                session, sender_account=q.sender_account, payee=q.payee, amount=q.amount,
                now=ctx.clock.now(), dpip_level=q.dpip_level, dpip_reasons=q.dpip_reasons,
            )  # fmt: skip
            return asdict(result)

        return frm(body, PaymentCheck, act)

    return app


def calibration_json(c: detection.Calibration) -> dict[str, Any]:
    return {
        "since": c.since.isoformat(),
        "until": c.until.isoformat(),
        "accounts": c.accounts,
        "known_bad": c.known_bad,
        "budget_per_day": c.budget_per_day,
        "expected_flags_per_day": c.expected_flags_per_day,
        "within_budget": c.within_budget,
        "proposal": asdict(c.proposal),
        "rules": [
            {
                "rule": t.rule.value,
                "title": detection.RULE_TITLES[t.rule],
                "chosen": t.chosen,
                "rows": [asdict(r) for r in t.rows],
            }
            for t in c.tables
        ],
    }


def _parse[M: BaseModel](model: type[M], opened: Opened) -> M:
    try:
        return model.model_validate(opened.payload)
    except ValidationError as exc:
        errors: list[dict[str, Any]] = [
            {"loc": e["loc"], "msg": e["msg"]} for e in exc.errors(include_url=False, include_input=False)
        ]
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, errors) from exc


def create_app() -> FastAPI:
    """The app `ripple up` starts, configured from the environment and `.ripple/`."""
    config = load_service_config()
    engine = make_engine(config.paths.database(config.member.id))
    stale = ledger.missing_columns(engine)
    if stale:
        raise SystemExit(
            f"{config.member.id}: the database in .ripple/data was made by an older Ripple (missing "
            f"{', '.join(stale)}). Run `uv run ripple up --fresh` to start with empty databases."
        )
    factory = init_db(engine, ledger.NodeBase.metadata)
    envelopes = Envelopes(
        load_signing_key(config.paths, config.member.id),
        load_keyring(config.paths),
        config.clock,
        SqlReplayGuard(factory),
    )
    member = config.member
    return build_app(
        NodeContext(member.id, factory, envelopes, config.clock, member.name, member.bank_code or "")
    )
