"""The bank node's HTTP service.

Routes take and return signed envelopes. Only the simulator ("sim") may open accounts and post transactions,
standing in for the core banking feed, and only the CFCFRMS hub may send notices. The officer routes are read-only
and only the web gateway ("web") may call them; the gateway checks the officer's role and bank.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from ripple_core.clock import Clock
from ripple_core.messages import AccountOpening, LedgerPosting, Notice
from ripple_core.signing import Opened
from ripple_core.tracing import LedgerError
from ripple_node import ledger, officer, responder
from ripple_service.config import load_keyring, load_service_config, load_signing_key
from ripple_service.db import SqlReplayGuard, init_db, make_engine, transaction
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


@dataclass(frozen=True)
class NodeContext:
    member_id: str
    factory: sessionmaker[Session]
    envelopes: Envelopes
    clock: Clock


def build_app(ctx: NodeContext) -> FastAPI:
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

    return app


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
    factory = init_db(make_engine(config.paths.database(config.member.id)), ledger.NodeBase.metadata)
    envelopes = Envelopes(
        load_signing_key(config.paths, config.member.id),
        load_keyring(config.paths),
        config.clock,
        SqlReplayGuard(factory),
    )
    return build_app(NodeContext(config.member.id, factory, envelopes, config.clock))
