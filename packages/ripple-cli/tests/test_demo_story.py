"""The PRD's demo story, end to end across the CFCFRMS hub and six institutions' nodes."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from netharness import Net
from ripple_core.clock import IST, FixedClock
from ripple_core.messages import AccountOpening, AccountRef, Complaint, ExitDetail, ExitMode, Payment, Rail
from ripple_core.money import rupees
from ripple_hubs.cfcfrms import Trail
from ripple_service.db import transaction, verify_audit

T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
ACK = "31234567890123"


def ref(ifsc: str, number: str, vpa: str | None = None) -> AccountRef:
    return AccountRef(ifsc=ifsc, account_number=number, vpa=vpa)


VICTIM = ("bank-a", ref("BKAA0000001", "100000000001"))
RAVI = ("bank-a", ref("BKAA0000002", "100000000002"))
M1 = ("bank-b", ref("BKBB0000001", "200000000001", "m1shop@bkbb"))
GALAXY = ("bank-b", ref("BKBB0000002", "200000000002", "galaxy.mobiles@bkbb"))
M2 = ("bank-c", ref("BKCC0000001", "300000000001"))
ASSISTANT = ("bank-c", ref("BKCC0000002", "300000000002"))
M3 = ("bank-d", ref("BKDD0000001", "400000000001"))
WALLET = ("wallet-w", ref("WLTW0000001", "500000000001"))
CRYPTO = ("exchange-x", ref("XCHX0000001", "600000000001"))


def at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


def pay(rail: Rail, reference: str, amount: int, minute: int) -> Payment:
    return Payment(rail=rail, reference=reference, amount=rupees(amount), at=at(minute))


@pytest.fixture
def net() -> Net:
    network = Net(FixedClock(T0 - timedelta(days=30)))
    opened = T0 - timedelta(days=30)
    for (member, account), holder, balance in [
        (VICTIM, "Retired teacher", 1_000_000),
        (RAVI, "Ravi Traders", 50_000),
        (M1, "M1", 0),
        (GALAXY, "Galaxy Mobiles", 20_000),
        (M2, "M2", 0),
        (ASSISTANT, "Shop assistant", 1_000),
        (M3, "M3 General Store", 300_000),
        (WALLET, "W wallet holder", 0),
        (CRYPTO, "X exchange customer", 0),
    ]:
        assert account.account_number
        assert account.ifsc
        network.open_account(
            member,
            AccountOpening(
                account_number=account.account_number,
                ifsc=account.ifsc,
                holder_name=holder,
                vpa=account.vpa,
                declared_profile="small shop" if holder.startswith("M3") else "",
                opening_balance=rupees(balance),
                opened_at=opened,
            ),
        )
    network.clock.advance(timedelta(days=30))

    victim_rtgs = pay(Rail.RTGS, "BKAAR20261020000000001", 800_000, 0)
    network.transfer(victim_rtgs, VICTIM, M1)
    network.transfer(pay(Rail.IMPS, "629301000001", 300_000, 2), M1, M2)
    network.transfer(pay(Rail.UPI, "629301000002", 250_000, 3), M1, M3)
    network.transfer(pay(Rail.IMPS, "629301000003", 150_000, 4), M1, WALLET)
    network.cash_out(
        "bank-c",
        "300000000001",
        pay(Rail.INTERNAL, "ATMW0001", 100_000, 5),
        ExitDetail(
            mode=ExitMode.ATM, reference="ATMW0001", identifier="S1BW000101", location="Ameerpet, Hyderabad"
        ),
    )
    network.transfer(pay(Rail.NEFT, "BKDDN26102000001", 200_000, 5), M3, RAVI)
    network.transfer(pay(Rail.IMPS, "629301000004", 100_000, 6), M2, CRYPTO)
    network.transfer(pay(Rail.UPI, "629301000005", 120_000, 6), M3, GALAXY)
    network.cash_out(
        "bank-c",
        "300000000001",
        pay(Rail.INTERNAL, "ATMW0002", 100_000, 7),
        ExitDetail(mode=ExitMode.ATM, reference="ATMW0002", identifier="S1BW000245", location="Secunderabad"),
    )
    network.transfer(pay(Rail.IMPS, "629301000006", 15_000, 8), M3, ASSISTANT)
    network.clock.advance(timedelta(minutes=12))
    return network


def file_complaint(net: Net) -> Trail:
    complaint = Complaint(
        ack_number=ACK,
        victim_name="Retired teacher",
        payment=pay(Rail.RTGS, "BKAAR20261020000000001", 800_000, 0),
        beneficiary=M1[1],
        filed_at=net.clock.now(),
    )
    net.call("web", "cfcfrms", "/v1/complaints", complaint)
    return Trail.model_validate(net.call("web", "cfcfrms", "/v1/trails", {"ack_number": ACK}).payload)


def test_the_trail_completes_and_every_rupee_is_accounted_for(net: Net) -> None:
    trail = file_complaint(net)

    assert trail.complete
    assert trail.reported == rupees(800_000)
    assert trail.held == rupees(600_000)
    assert trail.cashed_out == rupees(200_000)
    assert trail.off_network == trail.not_found == trail.waiting == 0
    held = {a.account.account_number: a.held for a in trail.accounts if a.held}
    assert held == {
        "200000000001": rupees(100_000),  # M1
        "500000000001": rupees(150_000),  # Wallet W
        "600000000001": rupees(100_000),  # the crypto exchange
        "100000000002": rupees(200_000),  # Ravi Traders, cleared later by the document review
        "200000000002": rupees(50_000),  # Galaxy Mobiles: only the traced part of Rs 1,20,000
    }
    atms = sorted(e.identifier for a in trail.accounts for e in a.exits)
    assert atms == ["S1BW000101", "S1BW000245"]


def test_the_holders_own_money_is_never_liened(net: Net) -> None:
    trail = file_complaint(net)

    on_trail = {a.account.account_number for a in trail.accounts}
    assert "300000000002" not in on_trail  # the assistant's salary was paid after the victim money ran out
    m3 = next(a for a in trail.accounts if a.account.account_number == "400000000001")
    assert m3.state == "answered"
    assert m3.held == 0
    assert m3.lien_id is None


def test_liened_money_cannot_be_spent(net: Net) -> None:
    file_complaint(net)
    with pytest.raises(Exception, match="409"):
        net.transfer(pay(Rail.IMPS, "629301000099", 50_000, 13), M1, M2)


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
