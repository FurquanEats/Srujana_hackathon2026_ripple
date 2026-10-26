"""Who is calling: a short-lived HS256 token the web app's server signs for each request.

The web app signs users in (Better Auth) and, for every gateway call, sends `X-Ripple-Session`: a compact JWT with
`sub`, `role`, `member` and `exp`, signed with the shared gateway secret. The gateway accepts only HS256, checks the
signature in constant time, and refuses tokens that have expired or that claim to live longer than five minutes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

MAX_LIFETIME = 300  # seconds
LEEWAY = 30  # seconds of clock difference tolerated between the web server and the gateway


class Role(StrEnum):
    NODAL_OFFICER = "nodal_officer"
    FRM_ANALYST = "frm_analyst"
    GRIEVANCE_OFFICER = "grievance_officer"
    POLICE_OFFICER = "police_officer"
    ACCOUNT_HOLDER = "account_holder"
    VICTIM = "victim"
    DEMO = "demo"


BANK_ROLES = frozenset({Role.NODAL_OFFICER, Role.FRM_ANALYST, Role.GRIEVANCE_OFFICER})


class AuthError(Exception):
    """The request does not carry a valid session."""


@dataclass(frozen=True)
class Session:
    sub: str
    role: Role
    member: str | None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except ValueError as exc:
        raise AuthError("malformed token") from exc


def issue(secret: bytes, *, sub: str, role: Role, member: str | None, now: int, lifetime: int = 120) -> str:
    """Sign a session token. The web app does the same in TypeScript; this is for tests and tools."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = {"sub": sub, "role": role.value, "member": member, "exp": now + lifetime}
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    signature = hmac.new(secret, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def verify(token: str, secret: bytes, now: int) -> Session:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("malformed token")
    try:
        header: dict[str, Any] = json.loads(_unb64(parts[0]))
        body: dict[str, Any] = json.loads(_unb64(parts[1]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthError("malformed token") from exc
    if header.get("alg") != "HS256":
        raise AuthError("unsupported algorithm")
    expected = hmac.new(secret, f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _unb64(parts[2])):
        raise AuthError("bad signature")
    exp = body.get("exp")
    if not isinstance(exp, int) or isinstance(exp, bool):
        raise AuthError("token has no expiry")
    if exp < now - LEEWAY:
        raise AuthError("token expired")
    if exp > now + MAX_LIFETIME + LEEWAY:
        raise AuthError("token lives too long")
    role_value = body.get("role")
    if not isinstance(role_value, str):
        raise AuthError("unknown role")
    try:
        role = Role(role_value)
    except ValueError as exc:
        raise AuthError("unknown role") from exc
    sub, member = body.get("sub"), body.get("member")
    if not isinstance(sub, str) or not sub or (member is not None and not isinstance(member, str)):
        raise AuthError("malformed claims")
    if role in BANK_ROLES and member is None:
        raise AuthError("a bank role needs an institution")
    return Session(sub, role, member)


def load_secret(path: Path, env_value: str | None) -> bytes:
    """The shared secret: from the environment if set, else from `.ripple/gateway.secret`, created if missing."""
    if env_value:
        return env_value.encode("utf-8")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48), encoding="ascii")
    return path.read_text(encoding="ascii").strip().encode("ascii")
