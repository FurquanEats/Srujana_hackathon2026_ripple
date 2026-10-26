"""The PRD's demo story, end to end across the CFCFRMS hub and six institutions' nodes."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from netharness import Net
from ripple_cli import demo
from ripple_core.clock import IST, FixedClock
from ripple_core.messages import Payment, Rail
from ripple_core.money import rupees
from ripple_hubs.cfcfrms import Trail
from ripple_service.db import transaction, verify_audit

T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
ACK = "31234567890123"


@pytest.fixture
def net() -> Net:
    network = Net(FixedClock(T0 - timedelta(days=30)))
    network.story = demo.seed(network.call, T0, "000001")  # type: ignore[attr-defined]
    network.clock.advance(timedelta(days=30, minutes=12))
    return network


def story(net: Net) -> demo.Story:
    result: demo.Story = net.story  # type: ignore[attr-defined]
    return result


def file_complaint(net: Net) -> Trail:
    net.call("web", "cfcfrms", "/v1/complaints", story(net).complaint(ACK, net.clock.now()))
    return Trail.model_validate(net.call("web", "cfcfrms", "/v1/trails", {"ack_number": ACK}).payload)


def test_the_trail_completes_and_every_rupee_is_accounted_for(net: Net) -> None:
    trail = file_complaint(net)

    assert trail.complete
    assert trail.reported == rupees(800_000)
    assert trail.held == rupees(600_000)
    assert trail.cashed_out == rupees(200_000)
    assert trail.off_network == trail.not_found == trail.waiting == 0
    held = {story(net).holder(a.account.account_number): a.held for a in trail.accounts if a.held}
    assert held == {
        "M1 (mule)": rupees(100_000),
        "Kunal Shah (wallet)": rupees(150_000),
        "Arvind Menon (crypto account)": rupees(100_000),
        "Ravi Traders (cement supplier)": rupees(200_000),  # cleared later by the document review
        "Galaxy Mobiles (phone shop)": rupees(50_000),  # only the traced part of Rs 1,20,000
    }
    atms = sorted(e.identifier for a in trail.accounts for e in a.exits)
    assert atms == ["S1BW000101", "S1BW000245"]


def test_the_holders_own_money_is_never_liened(net: Net) -> None:
    trail = file_complaint(net)

    on_trail = {story(net).holder(a.account.account_number) for a in trail.accounts}
    assert "M3's shop assistant" not in on_trail  # the salary was paid after the victim money ran out
    m3 = next(
        a for a in trail.accounts if story(net).holder(a.account.account_number).startswith("M3 General")
    )
    assert m3.state == "answered"
    assert m3.held == 0
    assert m3.lien_id is None


def test_liened_money_cannot_be_spent(net: Net) -> None:
    file_complaint(net)
    m1, m2 = story(net).parties["m1"].ref, story(net).parties["m2"].ref
    payment = Payment(rail=Rail.IMPS, reference="629301000099", amount=rupees(50_000), at=net.clock.now())
    with pytest.raises(Exception, match="409"):
        net.transfer(payment, ("bank-b", m1), ("bank-c", m2))


def test_repeating_a_complaint_does_not_double_the_liens(net: Net) -> None:
    first = file_complaint(net)
    second = file_complaint(net)
    assert second.held == first.held
    assert len(second.accounts) == len(first.accounts)


def test_every_node_keeps_an_intact_audit_chain(net: Net) -> None:
    file_complaint(net)
    for ctx in net.node_contexts.values():
        with transaction(ctx.factory) as session:
            assert verify_audit(session) is None


def test_only_the_hub_may_send_notices_and_only_the_simulator_may_post(net: Net) -> None:
    with pytest.raises(Exception, match="403"):
        net.call("web", "bank-b", "/v1/notices", {"anything": 1})
    with pytest.raises(Exception, match="403"):
        net.call("cfcfrms", "bank-b", "/v1/postings", {"postings": []})
    client: TestClient = net.clients["bank-b"]
    assert client.post("/v1/notices", json={"envelope": "a.b.c"}).status_code == 401
    assert client.post("/v1/notices", json={"wrong": "shape"}).status_code == 422


def test_the_mules_are_flagged_as_the_money_moves_before_anyone_reports(net: Net) -> None:
    """The PRD's story: Sangam Bank flags M3 by minute 9, because Rs 2,50,000 from a first-time payer left again
    within minutes from a small shop's account. Meridian Bank flags M1. Honest Ravi Traders and Galaxy Mobiles are
    not flagged."""
    m3 = net.call("web", "bank-d", "/v1/officer/cases", {}).payload["cases"]
    [case] = m3
    assert case["account_number"] == story(net).parties["m3"].ref.account_number
    assert {"pass_through", "out_of_profile"} <= set(case["rules"])
    assert max(f["at"] for f in case["flags"]) <= (T0 + timedelta(minutes=9)).isoformat()
    [m1] = net.call("web", "bank-b", "/v1/officer/cases", {}).payload["cases"]
    assert m1["holder_name"] == "M1 (mule)"
    flagged = {c["holder_name"] for bank in ("bank-a", "bank-b") for c in
               net.call("web", bank, "/v1/officer/cases", {}).payload["cases"]}  # fmt: skip
    assert "Ravi Traders (cement supplier)" not in flagged
    assert "Galaxy Mobiles (phone shop)" not in flagged


def test_the_frm_analyst_holds_m3s_flagged_credit_and_the_customer_is_told(net: Net) -> None:
    [case] = net.call("web", "bank-d", "/v1/officer/cases", {}).payload["cases"]
    hold = net.call("web", "bank-d", "/v1/officer/holds/place", {
        "actor": "frm-bank-d", "account_number": case["account_number"],
        "flag_keys": [f["key"] for f in case["flags"]], "contact": "Fraud Risk desk, Sangam Bank, 1800 000 0004",
    }).payload  # fmt: skip
    assert hold["status"] == "awaiting_explanation"
    assert hold["amount"] > 0
    assert "Dear M3 General Store (mule)" in hold["customer_notice"]
    [queued] = net.call("web", "bank-d", "/v1/officer/holds", {}).payload["holds"]
    assert queued["hold_id"] == hold["hold_id"]
    step = {
        "actor": "frm-bank-d",
        "hold_id": hold["hold_id"],
        "decision": "report",
        "reason": "too early",
    }
    with pytest.raises(Exception, match="409"):
        net.call("web", "bank-d", "/v1/officer/holds/decision", step)
