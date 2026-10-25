"""Pre-payment check and lien actions: a payment judged before it executes, and liens this bank places itself."""

import time

from fastapi.testclient import TestClient

from ripple import banks
from ripple.api.main import create_app


def wait_until(client, predicate, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.2)
    return False


def test_check_holds_a_coached_transfer_allows_an_ordinary_one_and_records_nothing():
    app = create_app(source="engine", data="sim:india", speed=1e9)
    with TestClient(app) as client:
        engine = app.state.engine
        assert wait_until(client, lambda: client.get("/health").json()["stats"]["processed"] > 8000, 60)
        broke = client.post("/inject/fd_broken").json()
        customer = broke["customer_account"]
        assert wait_until(client, lambda: any(e.counterparty.startswith("FD-")
                                              for e in engine.store.get(customer).incoming))

        state = engine.store.get(customer)
        processed = engine.processed
        held = client.post("/check", json={"src_account": customer, "dst_account": "SAFE-ACCOUNT-1",
                                           "amount": 750000, "rail": "RTGS"}).json()
        assert held["decision"] == "hold_and_call"
        assert any(r["code"] == "coerced_transfer" for r in held["reasons"]) and held["customer_message"]
        assert engine.store.get("SAFE-ACCOUNT-1") is None  # nothing recorded
        assert engine.store.get(customer) is state and engine.processed - processed < 50

        shop = next(iter(engine.store.get(customer).payees))
        ok = client.post("/check", json={"src_account": customer, "dst_account": shop, "amount": 450,
                                         "rail": "UPI"}).json()
        assert ok["decision"] == "allow" and ok["customer_message"] is None


def test_liens_are_placed_only_on_this_banks_accounts():
    client = TestClient(create_app(source="engine", data=""))
    own = next(a for a in (f"MULE{i:04d}" for i in range(1, 50)) if banks.bank_of(a) == banks.OWN)
    other = next(a for a in (f"MULE{i:04d}" for i in range(1, 50)) if banks.bank_of(a) != banks.OWN)
    lien = client.post("/liens", json={"plan_id": "C-0001", "account_id": own, "amount": 5000}).json()
    assert lien["status"] == "placed" and lien["bank"] == banks.OWN
    assert client.post("/liens", json={"plan_id": "C-0001", "account_id": own, "amount": 5000}).json() == lien
    refused = client.post("/liens", json={"plan_id": "C-0001", "account_id": other, "amount": 5000})
    assert refused.status_code == 409 and "CFCFRMS" in refused.json()["detail"]
    assert [x["account_id"] for x in client.get("/liens", params={"plan_id": "C-0001"}).json()] == [own]
    released = client.post(f"/liens/{lien['lien_id']}/release").json()
    assert released["status"] == "released"
