"""The gateway against the whole in-process network: sessions, roles, and every endpoint in the contract."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netharness import Net
from ripple_core.clock import IST, FixedClock
from ripple_gateway.app import GatewayContext, build_app
from ripple_gateway.auth import AuthError, Role, issue, load_secret, verify

SECRET = b"test-secret-of-sufficient-length-0123456789"
NOW = 1_800_000_000
T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)


@pytest.fixture
def net() -> Net:
    return Net(FixedClock(T0))


@pytest.fixture
def gw(net: Net) -> TestClient:
    return TestClient(build_app(GatewayContext(net.network, SECRET, net.call, net.clock, wall=lambda: NOW)))


def headers(role: Role, member: str | None = None, *, now: int = NOW, lifetime: int = 120) -> dict[str, str]:
    return {"X-Ripple-Session": issue(SECRET, sub="u1", role=role, member=member, now=now, lifetime=lifetime)}


DEMO = headers(Role.DEMO)
POLICE = headers(Role.POLICE_OFFICER)
BANK_B = headers(Role.NODAL_OFFICER, "bank-b")


def run_demo(gw: TestClient) -> str:
    response = gw.post("/v1/simulation/demo-story", headers=DEMO)
    assert response.status_code == 200, response.text
    ack: str = response.json()["ack_number"]
    return ack


def test_sessions_are_checked(gw: TestClient) -> None:
    missing = gw.get("/v1/me")
    assert missing.status_code == 401
    assert missing.json()["error"] == "unauthenticated"
    assert gw.get("/v1/me", headers=headers(Role.DEMO, now=NOW - 400)).status_code == 401  # expired
    assert gw.get("/v1/me", headers=headers(Role.DEMO, lifetime=3600)).status_code == 401  # lives too long
    assert (
        gw.get("/v1/me", headers=headers(Role.NODAL_OFFICER, None)).status_code == 401
    )  # bank role, no bank
    forged = issue(b"another-secret", sub="u1", role=Role.DEMO, member=None, now=NOW)
    assert gw.get("/v1/me", headers={"X-Ripple-Session": forged}).status_code == 401
    me = gw.get("/v1/me", headers=BANK_B).json()
    assert me == {
        "sub": "u1",
        "role": "nodal_officer",
        "member": "bank-b",
        "member_name": "Bank B, a private bank",
    }


def test_token_verification_rejects_other_algorithms_and_bad_claims() -> None:
    token = issue(SECRET, sub="u1", role=Role.DEMO, member=None, now=NOW)
    _header, body, sig = token.split(".")
    none_header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
    with pytest.raises(AuthError, match="algorithm"):
        verify(f"{none_header}.{body}.{sig}", SECRET, NOW)
    with pytest.raises(AuthError, match="malformed"):
        verify("not.a-token", SECRET, NOW)
    assert verify(token, SECRET, NOW).role is Role.DEMO


def test_roles_only_see_what_they_should(gw: TestClient) -> None:
    assert gw.get("/v1/cases", headers=BANK_B).status_code == 403
    assert gw.get("/v1/notices", headers=POLICE).status_code == 403
    assert gw.post("/v1/simulation/demo-story", headers=POLICE).status_code == 403
    hub_as_bank = headers(Role.NODAL_OFFICER, "cfcfrms")
    assert gw.get("/v1/notices", headers=hub_as_bank).status_code == 403


def test_the_demo_story_through_the_gateway(gw: TestClient) -> None:
    ack = run_demo(gw)

    cases = gw.get("/v1/cases", headers=POLICE).json()
    assert cases[0]["ack_number"] == ack
    assert cases[0]["held"] == 60_000_000
    assert cases[0]["complete"] is True

    trail = gw.get(f"/v1/cases/{ack}/trail", headers=POLICE).json()
    holders = {a["holder_name"] for a in trail["accounts"]}
    assert "M1 (mule)" in holders
    assert "Ravi Traders (cement supplier)" in holders
    assert gw.get("/v1/cases/31111111111111/trail", headers=POLICE).status_code == 404


def test_a_bank_officer_sees_its_notices_statement_and_liens(gw: TestClient) -> None:
    ack = run_demo(gw)

    notices = gw.get("/v1/notices", headers=BANK_B).json()
    by_holder = {n["holder_name"]: n for n in notices}
    assert set(by_holder) == {"M1 (mule)", "Galaxy Mobiles (phone shop)"}
    m1 = by_holder["M1 (mule)"]
    assert (m1["held"], m1["onward_count"], m1["ack_number"]) == (10_000_000, 3, ack)

    detail = gw.get(f"/v1/notices/{m1['notice_id']}", headers=BANK_B).json()
    assert detail["legal_basis"] == "BNSS s.168 read with s.94"
    traced = [line for line in detail["statement"] if line["victim_money"]]
    assert sum(line["victim_money"][ack] for line in traced if line["direction"] == "credit") == 80_000_000
    assert len(detail["onward"]) == 3

    liens = gw.get("/v1/liens", headers=BANK_B).json()
    assert sorted(lien["amount"] for lien in liens) == [5_000_000, 10_000_000]
    missing = gw.get("/v1/notices/no-such-notice", headers=BANK_B)
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"


def test_other_banks_notices_stay_private(gw: TestClient) -> None:
    run_demo(gw)
    bank_c = gw.get("/v1/notices", headers=headers(Role.NODAL_OFFICER, "bank-c")).json()
    assert {n["holder_name"] for n in bank_c} == {"M2 (mule)"}


def test_network_and_clock(gw: TestClient) -> None:
    members = gw.get("/v1/network", headers=POLICE).json()["members"]
    assert len(members) == 7
    assert datetime.fromisoformat(gw.get("/v1/clock", headers=POLICE).json()["now"]) == T0


def test_the_secret_is_created_once_and_reused(tmp_path: Path) -> None:
    path = tmp_path / "gateway.secret"
    first = load_secret(path, None)
    assert load_secret(path, None) == first
    assert len(first) >= 48
    assert load_secret(path, "from-env") == b"from-env"
