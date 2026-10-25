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
from pydantic import BaseModel

from ripple_cli import demo
from ripple_core.clock import Clock
from ripple_core.ids import ComplaintChannel, new_ncrp_ack
from ripple_core.messages import Complaint
from ripple_core.network import Kind, Network, load_network
from ripple_core.signing import MemoryReplayGuard, Opened
from ripple_gateway.auth import BANK_ROLES, AuthError, Role, Session, load_secret, verify
from ripple_service.config import Paths, clock_from_env, load_keyring, load_signing_key, repo_root
from ripple_service.transport import Courier, Envelopes, RemoteError, mtls_post

Caller = Callable[[str, str, str, BaseModel | dict[str, Any]], Opened]  # (party, member, path, payload)
POLICE_ROLES = frozenset({Role.POLICE_OFFICER, Role.DEMO})
HUB = "cfcfrms"
COMPLAINT_DELAY = timedelta(minutes=12)

AckPath = Annotated[str, Path(pattern=r"^[23]\d{13}$")]
NoticePath = Annotated[str, Path(min_length=8, max_length=64, pattern=r"^[0-9A-Za-z-]+$")]


@dataclass(frozen=True)
class GatewayContext:
    network: Network
    secret: bytes
    call: Caller
    clock: Clock  # the network's simulated clock
    wall: Callable[[], int] = field(default=lambda: int(time.time()))  # real time, for session expiry


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
    return build_app(GatewayContext(network, secret, caller, clock))
