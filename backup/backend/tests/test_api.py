from fastapi.testclient import TestClient

from ripple.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_cases_ordered_by_tier_then_expected_loss_and_cut_to_budget():
    cases = client.get("/cases", params={"budget": 3}).json()
    assert len(cases) == 3
    assert [c["tier"] for c in cases] == ["Critical", "Critical", "Review"]
    assert cases[0]["expected_loss"] >= cases[1]["expected_loss"]


def test_case_detail_and_unknown_case():
    assert client.get("/cases/C-0001").json()["tier"] == "Critical"
    assert client.get("/cases/C-9999").status_code == 404
    assert client.get("/cases/..\..\eval").status_code == 404  # never resolved as a path to another fixture


def test_feedback_rejects_bad_verdict():
    assert client.post("/cases/C-0001/feedback", json={"verdict": "maybe"}).status_code == 422
    assert client.post("/cases/C-0001/feedback", json={"verdict": "confirmed"}).json()["status"] == "confirmed"


def test_eval():
    assert "ablation" in client.get("/eval").json()


def test_stream_sends_scored_transactions():
    with client.websocket_connect("/ws/stream") as ws:
        event = ws.receive_json()
        assert event["type"] == "txn" and "probability" in event["txn"]
