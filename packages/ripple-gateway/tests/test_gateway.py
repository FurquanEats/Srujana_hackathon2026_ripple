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
        "member_name": "Meridian Private Bank, a private bank",
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


FRM_D = headers(Role.FRM_ANALYST, "bank-d")


def test_the_frm_analyst_works_a_mule_case_through_a_hold(gw: TestClient) -> None:
    run_demo(gw)
    assert gw.get("/v1/mule-cases", headers=BANK_B).status_code == 403  # nodal officers do not run mule holds
    [case] = gw.get("/v1/mule-cases", headers=FRM_D).json()
    assert case["holder_name"] == "M3 General Store (mule)"
    body = {"account_number": case["account_number"], "flag_keys": [f["key"] for f in case["flags"]],
            "contact": "Fraud Risk desk, Sangam Bank, 1800 000 0004"}  # fmt: skip
    hold = gw.post("/v1/holds", headers=FRM_D, json=body)
    assert hold.status_code == 200, hold.text
    hold_id = hold.json()["hold_id"]
    assert hold.json()["placed_by"] == "u1"
    again = gw.post("/v1/holds", headers=FRM_D, json=body)
    assert again.status_code == 409
    assert "already has a temporary debit hold" in again.json()["message"]
    explained = gw.post(f"/v1/holds/{hold_id}/explanation", headers=FRM_D, json={"summary": "Shop sales"})
    assert explained.json()["status"] == "explanation_received"
    released = gw.post(f"/v1/holds/{hold_id}/decision", headers=FRM_D,
                       json={"decision": "release", "reason": "Invoices match"})  # fmt: skip
    assert released.json()["status"] == "released"
    assert gw.post("/v1/holds/HNOTAVALIDID/decision", headers=FRM_D, json={}).status_code == 422
    [queued] = gw.get("/v1/holds", headers=FRM_D).json()
    assert queued["released_at"] is not None


def test_the_shadow_run_proposes_settings_the_frm_head_approves(gw: TestClient) -> None:
    run_demo(gw)
    run = gw.post("/v1/detection/shadow-run", headers=FRM_D, json={"budget_per_day": 20}).json()
    assert {r["rule"] for r in run["rules"]} == {
        "pass_through", "many_new_senders", "out_of_profile", "dormant_then_busy", "quick_cash_out"
    }  # fmt: skip
    assert run["within_budget"]
    approved = gw.post(
        "/v1/detection/thresholds", headers=FRM_D, json={**run["proposal"], "budget_per_day": 20}
    )
    assert approved.status_code == 200, approved.text
    assert gw.get("/v1/detection/thresholds", headers=FRM_D).json() == run["proposal"]


def place_m3_hold(gw: TestClient) -> tuple[str, str]:
    [case] = gw.get("/v1/mule-cases", headers=FRM_D).json()
    body = {"account_number": case["account_number"], "flag_keys": [f["key"] for f in case["flags"]],
            "contact": "Fraud Risk desk, Sangam Bank, 1800 000 0004"}  # fmt: skip
    hold = gw.post("/v1/holds", headers=FRM_D, json=body).json()
    return case["account_number"], hold["hold_id"]


def victim_and_m1(gw: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    """The victim's and M1's account references, as M1's bank statement shows them."""
    notices = gw.get("/v1/notices", headers=BANK_B).json()
    m1 = next(n for n in notices if n["holder_name"] == "M1 (mule)")
    detail = gw.get(f"/v1/notices/{m1['notice_id']}", headers=BANK_B).json()
    victim = next(line["counterparty"] for line in detail["statement"] if line["direction"] == "credit")
    m1_ref = {"ifsc": "BKBB0000001", "account_number": m1["account_number"], "vpa": None}
    return victim, m1_ref


def test_the_payment_check_stops_the_next_victim_paying_a_reported_mule(gw: TestClient) -> None:
    run_demo(gw)
    victim, m1 = victim_and_m1(gw)
    frm_a = headers(Role.FRM_ANALYST, "bank-a")
    body = {"sender_account": victim["account_number"], "payee": m1, "amount": 40_000_000}
    answer = gw.post("/v1/payment-check", headers=frm_a, json=body)
    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result["decision"] == "hold_and_call"
    assert result["dpip_level"] == "very_high"
    assert any("suspect registry" in r["text"] for r in result["reasons"])
    assert gw.post("/v1/payment-check", headers=POLICE, json=body).status_code == 403


def test_a_hold_publishes_a_dpip_signal_by_hashes_only(gw: TestClient) -> None:
    run_demo(gw)
    m3_account, _hold_id = place_m3_hold(gw)
    victim, _m1 = victim_and_m1(gw)
    m3 = {"ifsc": "BKDD0000001", "account_number": m3_account, "vpa": None}
    body = {"sender_account": victim["account_number"], "payee": m3, "amount": 1_000_000}
    result = gw.post("/v1/payment-check", headers=headers(Role.NODAL_OFFICER, "bank-a"), json=body).json()
    assert any("member bank reported it" in r["text"] for r in result["reasons"])
    assert result["decision"] == "hold_and_call"


def test_the_audit_log_shows_each_hold_step_and_an_intact_chain(gw: TestClient) -> None:
    run_demo(gw)
    place_m3_hold(gw)
    audit = gw.get("/v1/audit", headers=FRM_D).json()
    assert audit["broken_at"] is None
    assert "hold.place" in {e["action"] for e in audit["entries"]}
    assert gw.get("/v1/audit", headers=POLICE).status_code == 403


def test_the_account_holder_sees_the_notice_and_explains(gw: TestClient) -> None:
    run_demo(gw)
    account, hold_id = place_m3_hold(gw)
    holder = {
        "X-Ripple-Session": issue(SECRET, sub=account, role=Role.ACCOUNT_HOLDER, member="bank-d", now=NOW)
    }
    [mine] = gw.get("/v1/my-holds", headers=holder).json()
    assert mine["hold_id"] == hold_id
    assert "str_draft" not in mine
    assert "Dear M3 General Store" in mine["customer_notice"]
    sent = gw.post(
        f"/v1/my-holds/{hold_id}/explanation", headers=holder, json={"summary": "Shop sales; bills attached"}
    )
    assert sent.json()["status"] == "explanation_received"
    stranger = {
        "X-Ripple-Session": issue(
            SECRET, sub="1234567890", role=Role.ACCOUNT_HOLDER, member="bank-d", now=NOW
        )
    }
    assert gw.get("/v1/my-holds", headers=stranger).json() == []
    assert (
        gw.post(f"/v1/my-holds/{hold_id}/explanation", headers=stranger, json={"summary": "x"}).status_code
        == 404
    )


def test_the_victim_sees_what_is_held_without_the_mules_details(gw: TestClient) -> None:
    ack = run_demo(gw)
    victim = {"X-Ripple-Session": issue(SECRET, sub=ack, role=Role.VICTIM, member=None, now=NOW)}
    status = gw.get("/v1/my-complaint", headers=victim).json()
    assert (status["reported"], status["held"], status["cashed_out"]) == (80_000_000, 60_000_000, 20_000_000)
    assert all("account" not in p and "holder_name" not in p for p in status["places"])
    assert gw.get("/v1/my-complaint", headers=POLICE).status_code == 403


def test_the_police_see_reported_holds_and_instruct_the_bank(gw: TestClient) -> None:
    run_demo(gw)
    _account, hold_id = place_m3_hold(gw)
    police = headers(Role.POLICE_OFFICER)
    assert gw.get("/v1/hold-reports", headers=police).json() == []
    gw.post(f"/v1/holds/{hold_id}/explanation", headers=FRM_D, json={"summary": "None that fits the credits"})
    gw.post(f"/v1/holds/{hold_id}/decision", headers=FRM_D, json={"decision": "report", "reason": "No fit"})
    [report] = gw.get("/v1/hold-reports", headers=police).json()
    assert (report["member"], report["hold_id"]) == ("bank-d", hold_id)
    done = gw.post(f"/v1/hold-reports/bank-d/{hold_id}/instruction", headers=police,
                   json={"instruction": "continue", "authority": "Cyber Crime PS, Hyderabad"})  # fmt: skip
    assert done.json()["status"] == "held_on_police_instruction"
    assert gw.post(f"/v1/hold-reports/bank-z/{hold_id}/instruction", headers=police,
                   json={"instruction": "continue", "authority": "x" * 5}).status_code == 404  # fmt: skip


def test_the_officer_opens_an_account_with_its_statement_flags_and_holds(gw: TestClient) -> None:
    run_demo(gw)
    account, hold_id = place_m3_hold(gw)
    view = gw.get(f"/v1/accounts/{account}", headers=FRM_D).json()
    assert view["holder_name"] == "M3 General Store (mule)"
    assert view["on_hold"] > 0
    assert view["available"] == view["balance"] - view["liened"] - view["on_hold"]
    assert [h["hold_id"] for h in view["holds"]] == [hold_id]
    assert view["flags"]
    assert view["statement"]
    assert gw.get("/v1/accounts/0000000000", headers=FRM_D).status_code == 404
    assert gw.get(f"/v1/accounts/{account}", headers=POLICE).status_code == 403


def test_the_police_return_liened_money_to_the_victim(gw: TestClient) -> None:
    ack = run_demo(gw)
    trail = gw.get(f"/v1/cases/{ack}/trail", headers=POLICE).json()
    m1 = next(a for a in trail["accounts"] if a["holder_name"] == "M1 (mule)")
    order = {"authority": "Cyber Crime PS, Hyderabad", "order": "CCPS/106/2026/41",
             "reason": "Interim custody to the victim", "to_victim": True}  # fmt: skip
    done = gw.post(f"/v1/police/liens/{m1['member']}/{m1['lien_id']}/release", headers=POLICE, json=order)
    assert done.status_code == 200, done.text
    again = gw.post(f"/v1/police/liens/{m1['member']}/{m1['lien_id']}/release", headers=POLICE, json=order)
    assert again.status_code == 409
    victim = {"X-Ripple-Session": issue(SECRET, sub=ack, role=Role.VICTIM, member=None, now=NOW)}
    assert gw.get("/v1/my-complaint", headers=victim).json()["returned"] == 10_000_000
    [lien] = [x for x in gw.get("/v1/liens", headers=BANK_B).json() if x["lien_id"] == m1["lien_id"]]
    assert (lien["release_order"], lien["returned_to_victim"]) == ("CCPS/106/2026/41", True)
    assert gw.post(f"/v1/liens/{m1['lien_id']}/release", headers=FRM_D, json=order).status_code == 403


def test_hold_notes_and_call_backs_land_on_the_hold(gw: TestClient) -> None:
    run_demo(gw)
    account, hold_id = place_m3_hold(gw)
    gw.post(f"/v1/holds/{hold_id}/note", headers=FRM_D, json={"note": "Called the customer; no answer."})
    holder = {
        "X-Ripple-Session": issue(SECRET, sub=account, role=Role.ACCOUNT_HOLDER, member="bank-d", now=NOW)
    }
    asked = gw.post(f"/v1/my-holds/{hold_id}/call-back", headers=holder, json={"note": "After 5 pm, please"})
    assert asked.status_code == 200, asked.text
    [hold] = gw.get("/v1/holds", headers=FRM_D).json()
    assert [n["note"] for n in hold["notes"]] == [
        "Called the customer; no answer.",
        "Customer asked for a call back: After 5 pm, please",
    ]


def test_threshold_history_keeps_every_approval(gw: TestClient) -> None:
    run_demo(gw)
    settings = {"pass_through_minutes": 45, "new_senders": 4, "profile_multiple": 2.5, "dormant_days": 60,
                "cash_out_minutes": 90}  # fmt: skip
    gw.post("/v1/detection/thresholds", headers=FRM_D, json={**settings, "budget_per_day": 8})
    [entry] = gw.get("/v1/detection/history", headers=FRM_D).json()
    assert (entry["settings"], entry["budget_per_day"], entry["approved_by"]) == (settings, 8, "u1")
