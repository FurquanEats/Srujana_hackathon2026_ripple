"""The web gateway: plain JSON on 127.0.0.1 for the web app's server, signed envelopes over mutual TLS to the network.

Every request carries the web app's session token (see `auth`). The gateway checks the caller's role and bank, then
calls bank nodes and the CFCFRMS hub as the party "web". A bank role only ever reaches its own bank's node.
The contract is "03 Gateway API contract" in the team's shared folder; responses keep exactly those shapes.

This module does not use postponed annotations: FastAPI must see the session dependency type defined inside
`build_app`.
"""

import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ripple_cli import demo
from ripple_core.clock import Clock
from ripple_core.dpip import identifier_hashes, load_key
from ripple_core.ids import ComplaintChannel, new_ncrp_ack
from ripple_core.messages import AccountRef, Complaint, RiskLevel, RiskSignal
from ripple_core.network import Kind, Network, load_network
from ripple_core.signing import MemoryReplayGuard, Opened
from ripple_gateway.auth import BANK_ROLES, AuthError, Role, Session, load_secret, verify
from ripple_service.config import Paths, clock_from_env, load_keyring, load_signing_key, repo_root
from ripple_service.transport import Courier, Envelopes, RemoteError, mtls_post

Caller = Callable[[str, str, str, BaseModel | dict[str, Any]], Opened]  # (party, member, path, payload)
POLICE_ROLES = frozenset({Role.POLICE_OFFICER, Role.DEMO})
HUB = "cfcfrms"
COMPLAINT_DELAY = timedelta(minutes=12)

FRM_ROLES = frozenset({Role.FRM_ANALYST})
CHECK_ROLES = frozenset({Role.FRM_ANALYST, Role.NODAL_OFFICER})
# What an account holder may see of their own hold: no STR draft, no internal grounds, no officer names.
CUSTOMER_FIELDS = ("hold_id", "account_number", "holder_name", "amount", "whole_account", "reasons",
                   "contact", "customer_notice", "placed_at", "status", "deadlines", "next_deadline",
                   "expires_at", "explanation", "explanation_at", "decision", "decision_reason",
                   "released_at", "release_reason", "reported_at")  # fmt: skip

AckPath = Annotated[str, Path(pattern=r"^[23]\d{13}$")]
HoldPath = Annotated[str, Path(pattern=r"^H[0-9A-F]{16}$")]
AccountPath = Annotated[str, Path(pattern=r"^[0-9A-Z]{6,20}$")]


class Body(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DismissBody(Body):
    reason: Annotated[str, Field(min_length=10, max_length=2000)]


class HoldBody(Body):
    account_number: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]
    flag_keys: Annotated[list[str], Field(min_length=1, max_length=50)]
    contact: Annotated[str, Field(min_length=5, max_length=200)]
    whole_account: bool = False
    account_level_reason: Annotated[str, Field(max_length=2000)] | None = None


class ExplanationBody(Body):
    summary: Annotated[str, Field(min_length=1, max_length=2000)]


class DecisionBody(Body):
    decision: Annotated[str, Field(pattern=r"^(release|report)$")]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class InstructionBody(Body):
    instruction: Annotated[str, Field(pattern=r"^(release|continue)$")]
    authority: Annotated[str, Field(min_length=3, max_length=200)]


class GroundsBody(Body):
    grounds: Annotated[str, Field(min_length=1, max_length=2000)]


class StrFiledBody(Body):
    reference: Annotated[str, Field(min_length=3, max_length=64)]


class ShadowRunBody(Body):
    budget_per_day: Annotated[float, Field(gt=0, le=10_000)]


class ThresholdsBody(Body):
    budget_per_day: Annotated[float, Field(gt=0, le=10_000)] | None = None
    pass_through_minutes: Annotated[int, Field(ge=1, le=10_080)]
    new_senders: Annotated[int, Field(ge=2, le=1_000)]
    profile_multiple: Annotated[float, Field(gt=0, le=1_000)]
    dormant_days: Annotated[int, Field(ge=1, le=3_650)]
    cash_out_minutes: Annotated[int, Field(ge=1, le=10_080)]


class PaymentCheckBody(Body):
    sender_account: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]
    payee: AccountRef
    amount: Annotated[int, Field(gt=0, le=10**13)]


MemberPath = Annotated[str, Path(pattern=r"^[a-z]+-[a-z]$")]
NoticePath = Annotated[str, Path(min_length=8, max_length=64, pattern=r"^[0-9A-Za-z-]+$")]


@dataclass(frozen=True)
class GatewayContext:
    network: Network
    secret: bytes
    call: Caller
    clock: Clock  # the network's simulated clock
    wall: Callable[[], int] = field(default=lambda: int(time.time()))  # real time, for session expiry
    dpip_key: bytes = b"ripple-test-dpip-key"  # the network's shared key for DPIP identifier hashes


def build_app(ctx: GatewayContext) -> FastAPI:  # noqa: PLR0915 - one short function per route
    app = FastAPI(title="Ripple web gateway", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        codes = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "invalid"}
        return JSONResponse(
            {"error": codes.get(exc.status_code, "upstream_error"), "message": str(exc.detail)},
            status_code=exc.status_code,
        )

    def session(x_ripple_session: Annotated[str | None, Header()] = None) -> Session:
        if not x_ripple_session:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
        try:
            return verify(x_ripple_session, ctx.secret, ctx.wall())
        except AuthError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "The session is not valid. Sign in again."
            ) from exc

    Who = Annotated[Session, Depends(session)]  # noqa: N806 - a type alias, named like one

    def allow(who: Session, roles: frozenset[Role]) -> None:
        if who.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This role cannot see this information.")

    def own_bank(who: Session) -> str:
        allow(who, BANK_ROLES)
        try:
            member = ctx.network.get(who.member or "")
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "The session names an unknown institution."
            ) from exc
        if member.kind is Kind.HUB:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "A bank role must belong to an institution.")
        return member.id

    def call(party: str, member: str, path: str, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
        try:
            return ctx.call(party, member, path, payload).payload
        except RemoteError as exc:
            if exc.status in (404, 409, 422):
                raise HTTPException(exc.status, exc.detail) from exc
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{member} could not answer.") from exc
        except ConnectionError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{member} is not reachable.") from exc

    @app.get("/v1/me")
    def me(who: Who) -> dict[str, Any]:
        name = None
        if who.member:
            try:
                name = ctx.network.get(who.member).name
            except KeyError:
                name = None
        return {"sub": who.sub, "role": who.role.value, "member": who.member, "member_name": name}

    @app.get("/v1/clock")
    def clock(_who: Who) -> dict[str, str]:
        return {"now": ctx.clock.now().isoformat()}

    @app.get("/v1/network")
    def network(_who: Who) -> dict[str, Any]:
        return {
            "members": [
                {"id": m.id, "name": m.name, "kind": m.kind.value, "bank_code": m.bank_code}
                for m in ctx.network.members
            ]
        }

    @app.get("/v1/notices")
    def notices(who: Who) -> list[Any]:
        result: list[Any] = call("web", own_bank(who), "/v1/officer/notices", {})["notices"]
        return result

    @app.get("/v1/notices/{notice_id}")
    def notice(who: Who, notice_id: NoticePath) -> dict[str, Any]:
        return call("web", own_bank(who), "/v1/officer/notice", {"notice_id": notice_id})

    @app.get("/v1/liens")
    def liens(who: Who) -> list[Any]:
        result: list[Any] = call("web", own_bank(who), "/v1/officer/liens", {})["liens"]
        return result

    def frm_bank(who: Session) -> str:
        allow(who, FRM_ROLES)
        return own_bank(who)

    def hold_step(who: Session, hold_id: str, path: str, body: Body) -> dict[str, Any]:
        payload = {**body.model_dump(), "actor": who.sub, "hold_id": hold_id}
        return call("web", frm_bank(who), f"/v1/officer/holds/{path}", payload)

    @app.get("/v1/mule-cases")
    def mule_cases(who: Who, include_closed: bool = False) -> list[Any]:
        result: list[Any] = call(
            "web", frm_bank(who), "/v1/officer/cases", {"include_closed": include_closed}
        )["cases"]
        return result

    @app.post("/v1/mule-cases/{account_number}/dismiss")
    def dismiss_case(who: Who, account_number: AccountPath, body: DismissBody) -> dict[str, Any]:
        payload = {"actor": who.sub, "account_number": account_number, "reason": body.reason}
        return call("web", frm_bank(who), "/v1/officer/cases/dismiss", payload)

    @app.get("/v1/holds")
    def hold_queue(who: Who) -> list[Any]:
        result: list[Any] = call("web", frm_bank(who), "/v1/officer/holds", {})["holds"]
        return result

    def publish(hold: dict[str, Any], level: RiskLevel, reason_code: str) -> None:
        """Tell DPIP about a suspected mule by keyed hashes only (PRD P3). A failure never undoes the hold."""
        ref = hold.get("account_ref")
        expires = hold.get("expires_at")
        if not ref or not expires:
            return
        signal = RiskSignal(
            identifier_hashes=identifier_hashes(ctx.dpip_key, AccountRef.model_validate(ref)),
            level=level, reason_code=reason_code, expires_at=expires,
        )  # fmt: skip
        try:
            ctx.call("web", HUB, "/v1/dpip/signals", signal)
        except (RemoteError, ConnectionError):
            return

    @app.post("/v1/holds")
    def place_hold(who: Who, body: HoldBody) -> dict[str, Any]:
        hold = call("web", frm_bank(who), "/v1/officer/holds/place", {**body.model_dump(), "actor": who.sub})
        publish(hold, RiskLevel.HIGH, "temporary_debit_hold")
        return hold

    @app.post("/v1/holds/{hold_id}/explanation")
    def hold_explanation(who: Who, hold_id: HoldPath, body: ExplanationBody) -> dict[str, Any]:
        return hold_step(who, hold_id, "explanation", body)

    @app.post("/v1/holds/{hold_id}/decision")
    def hold_decision(who: Who, hold_id: HoldPath, body: DecisionBody) -> dict[str, Any]:
        return hold_step(who, hold_id, "decision", body)

    @app.post("/v1/holds/{hold_id}/police-instruction")
    def hold_instruction(who: Who, hold_id: HoldPath, body: InstructionBody) -> dict[str, Any]:
        return hold_step(who, hold_id, "instruction", body)

    @app.post("/v1/holds/{hold_id}/confirm-mule")
    def hold_confirm(who: Who, hold_id: HoldPath, body: GroundsBody) -> dict[str, Any]:
        hold = hold_step(who, hold_id, "confirm-mule", body)
        publish(hold, RiskLevel.VERY_HIGH, "confirmed_mule")
        return hold

    @app.post("/v1/holds/{hold_id}/str-filed")
    def hold_str_filed(who: Who, hold_id: HoldPath, body: StrFiledBody) -> dict[str, Any]:
        return hold_step(who, hold_id, "str-filed", body)

    @app.get("/v1/detection/thresholds")
    def thresholds(who: Who) -> dict[str, Any]:
        return call("web", frm_bank(who), "/v1/officer/detection/thresholds", {})

    @app.post("/v1/detection/shadow-run")
    def shadow_run(who: Who, body: ShadowRunBody) -> dict[str, Any]:
        return call("web", frm_bank(who), "/v1/officer/detection/shadow-run", body.model_dump())

    @app.post("/v1/detection/thresholds")
    def approve_thresholds(who: Who, body: ThresholdsBody) -> dict[str, Any]:
        payload = {**body.model_dump(), "actor": who.sub}
        return call("web", frm_bank(who), "/v1/officer/detection/approve", payload)

    @app.get("/v1/cases")
    def cases(who: Who) -> list[Any]:
        allow(who, POLICE_ROLES)
        result: list[Any] = call("web", HUB, "/v1/cases", {})["cases"]
        return result

    @app.get("/v1/cases/{ack_number}/trail")
    def trail(who: Who, ack_number: AckPath) -> dict[str, Any]:
        allow(who, POLICE_ROLES)
        return call("web", HUB, "/v1/trails", {"ack_number": ack_number})

    @app.post("/v1/complaints")
    def complaint(who: Who, body: Complaint) -> dict[str, Any]:
        allow(who, POLICE_ROLES)
        return call("web", HUB, "/v1/complaints", body)

    @app.get("/v1/audit")
    def audit(who: Who, limit: int = 200) -> dict[str, Any]:
        return call("web", own_bank(who), "/v1/officer/audit", {"limit": max(1, min(limit, 1000))})

    @app.post("/v1/payment-check")
    def payment_check(who: Who, body: PaymentCheckBody) -> dict[str, Any]:
        """Ask DPIP about the payee by keyed hashes, then let the bank's node weigh it with the sender's history."""
        allow(who, CHECK_ROLES)
        bank = own_bank(who)
        hashes = identifier_hashes(ctx.dpip_key, body.payee)
        if not hashes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the payee's account and IFSC, or a UPI ID."
            )
        started = time.perf_counter()
        dpip = call("web", HUB, "/v1/dpip/check", {"identifier_hashes": hashes})
        dpip_ms = round((time.perf_counter() - started) * 1000)
        payload = {
            **body.model_dump(mode="json"),
            "dpip_level": dpip["level"],
            "dpip_reasons": dpip["reasons"],
        }
        result = call("web", bank, "/v1/officer/payment-check", payload)
        return {**result, "dpip_level": dpip["level"], "dpip_ms": dpip_ms}

    def holder_account(who: Session) -> tuple[str, str]:
        """An account holder's bank and account number: the session's institution and subject."""
        allow(who, frozenset({Role.ACCOUNT_HOLDER}))
        if not who.member or not who.sub.isalnum():
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "An account holder session names a bank and an account."
            )
        return who.member, who.sub

    def customer_view(hold: dict[str, Any]) -> dict[str, Any]:
        """What the customer may see: no STR draft, no internal grounds, no officer names."""
        return {k: hold.get(k) for k in CUSTOMER_FIELDS}

    def own_holds(who: Session) -> tuple[str, list[dict[str, Any]]]:
        bank, account = holder_account(who)
        rows: list[dict[str, Any]] = call("web", bank, "/v1/officer/holds", {})["holds"]
        return bank, [h for h in rows if h["account_number"] == account]

    @app.get("/v1/my-holds")
    def my_holds(who: Who) -> list[Any]:
        _bank, rows = own_holds(who)
        return [customer_view(h) for h in rows]

    @app.post("/v1/my-holds/{hold_id}/explanation")
    def my_explanation(who: Who, hold_id: HoldPath, body: ExplanationBody) -> dict[str, Any]:
        bank, rows = own_holds(who)
        if not any(h["hold_id"] == hold_id for h in rows):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such hold on your account.")
        payload = {"summary": body.summary, "actor": f"customer:{who.sub}"[:64], "hold_id": hold_id}
        return customer_view(call("web", bank, "/v1/officer/holds/explanation", payload))

    @app.get("/v1/my-complaint")
    def my_complaint(who: Who) -> dict[str, Any]:
        """A victim's own complaint: what is held and where, without the mule accounts' details."""
        allow(who, frozenset({Role.VICTIM}))
        trail = call("web", HUB, "/v1/trails", {"ack_number": who.sub})
        names = {m.id: m.name for m in ctx.network.members}
        places = [
            {"member": a["member"], "institution": names.get(a["member"] or "", "Outside the network"),
             "layer": a["layer"], "held": a["held"], "state": a["state"],
             "cashed_out": sum(e["traced_amount"] for e in a["exits"])}
            for a in trail["accounts"]
        ]  # fmt: skip
        totals = {
            k: trail[k] for k in ("reported", "held", "cashed_out", "off_network", "not_found", "waiting")
        }
        return {"ack_number": trail["ack_number"], **totals, "complete": trail["complete"], "places": places}

    def bank_members() -> list[str]:
        return [m.id for m in ctx.network.members if m.kind is not Kind.HUB]

    @app.get("/v1/hold-reports")
    def hold_reports(who: Who) -> list[Any]:
        """Temporary debit holds that banks reported to the police, across every bank (police only)."""
        allow(who, frozenset({Role.POLICE_OFFICER}))
        names = {m.id: m.name for m in ctx.network.members}
        reports: list[Any] = []
        for member in bank_members():
            try:
                rows = call("web", member, "/v1/officer/holds", {})["holds"]
            except HTTPException:
                continue
            reports += [
                {**customer_view(h), "member": member, "member_name": names[member],
                 "instruction": h.get("instruction"), "str_filed_at": h.get("str_filed_at"),
                 "mule_confirmed_at": h.get("mule_confirmed_at")}
                for h in rows if h.get("reported_at")
            ]  # fmt: skip
        return reports

    @app.post("/v1/hold-reports/{member}/{hold_id}/instruction")
    def police_instruction(
        who: Who, member: MemberPath, hold_id: HoldPath, body: InstructionBody
    ) -> dict[str, Any]:
        allow(who, frozenset({Role.POLICE_OFFICER}))
        if member not in bank_members():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such bank on the network.")
        payload = {**body.model_dump(), "actor": who.sub, "hold_id": hold_id}
        return customer_view(call("web", member, "/v1/officer/holds/instruction", payload))

    @app.post("/v1/simulation/demo-story")
    def demo_story(who: Who) -> dict[str, str]:
        """Seed the PRD's demo story on the network and file its complaint (demo role only)."""
        allow(who, frozenset({Role.DEMO}))
        now = ctx.clock.now()

        def seed_call(party: str, member: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
            call(party, member, path, payload)
            return Opened(party, member, now, "", {})

        story = demo.seed(seed_call, now - COMPLAINT_DELAY, f"{secrets.randbelow(10**6):06d}")
        ack = new_ncrp_ack(ComplaintChannel.HELPLINE_1930)
        call("web", HUB, "/v1/complaints", story.complaint(ack, ctx.clock.now()))
        return {"ack_number": ack}

    return app


def create_app() -> FastAPI:
    """The app `ripple up` starts on 127.0.0.1:8090."""
    root = repo_root()
    network = load_network(root / "network.toml")
    paths = Paths(root / ".ripple")
    clock = clock_from_env()
    keyring = load_keyring(paths)
    couriers = {
        party: Courier(
            Envelopes(load_signing_key(paths, party), keyring, clock, MemoryReplayGuard()),
            mtls_post(network, paths, party),
        )
        for party in ("web", "sim")
    }

    def caller(party: str, member: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
        return couriers[party].call(member, path, payload)

    secret = load_secret(paths.home / "gateway.secret", os.environ.get("GATEWAY_SECRET"))
    dpip_key = load_key(paths.home / "dpip.key")
    return build_app(GatewayContext(network, secret, caller, clock, dpip_key=dpip_key))
