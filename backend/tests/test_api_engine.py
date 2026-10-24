"""The API with the live engine: ingest, cases, detail, feedback, stream, and replay from a file."""

import scenarios as s
from fastapi.testclient import TestClient

from ripple.api.main import create_app
from ripple.stream import load_transactions


def ring_payload():
    b = s.Builder()
    ring = s.mule_ring(b)
    return [t.model_dump(mode="json") for t in b.sorted()], ring


def test_ingest_then_cases_detail_and_feedback():
    client = TestClient(create_app(source="engine", data=""))
    payload, ring = ring_payload()
    scored = client.post("/ingest", json=payload).json()
    assert len(scored) == len(payload)

    cases = client.get("/cases").json()
    top = cases[0]
    assert top["tier"] == "Critical"
    detail = client.get(f"/cases/{top['case_id']}").json()
    assert ring["hop"][1] in {t["txn_id"] for t in detail["timeline"]}

    result = client.post(f"/cases/{top['case_id']}/feedback", json={"verdict": "confirmed"}).json()
    assert result["status"] == "confirmed"
    assert top["case_id"] not in {c["case_id"] for c in client.get("/cases").json()}
    assert client.get("/stats").json()["processed"] == len(payload)


def test_stream_pushes_ingested_transactions():
    client = TestClient(create_app(source="engine", data=""))
    payload, _ = ring_payload()
    with client.websocket_connect("/ws/stream") as ws:
        client.post("/ingest", json=payload[:1])
        event = ws.receive_json()
    assert event["type"] == "txn" and event["txn"]["txn_id"] == payload[0]["txn_id"]


def test_ingest_refused_in_fixture_mode():
    client = TestClient(create_app(source="fixtures"))
    assert client.post("/ingest", json=[]).status_code == 409


def test_load_transactions_from_csv(tmp_path):
    payload, _ = ring_payload()
    path = tmp_path / "txns.csv"
    import pandas as pd

    pd.DataFrame(payload).to_csv(path, index=False)
    txns = load_transactions(path)
    assert len(txns) == len(payload)
    assert [t.ts for t in txns] == sorted(t.ts for t in txns)
