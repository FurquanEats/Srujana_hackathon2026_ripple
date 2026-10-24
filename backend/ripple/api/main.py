"""FastAPI entrypoint: REST routes for cases, feedback and evaluation, and the /ws/stream WebSocket."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ripple import fixtures
from ripple.schema import CaseDetail, CaseSummary, EvalReport, Feedback, FeedbackResult, Layer

app = FastAPI(title="Ripple", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("RIPPLE_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "source": "fixtures"}


@app.get("/cases")
def list_cases(budget: int = Query(50, ge=1, le=1000)) -> list[CaseSummary]:
    """Open cases, highest expected loss first, cut to the alert budget."""
    cases = sorted(fixtures.cases(), key=lambda c: c.expected_loss, reverse=True)
    return cases[:budget]


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> CaseDetail:
    case = fixtures.case_detail(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
    return case


@app.post("/cases/{case_id}/feedback")
def post_feedback(case_id: str, feedback: Feedback) -> FeedbackResult:
    if case_id not in {c.case_id for c in fixtures.cases()}:
        raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
    # Placeholder until ripple.feedback updates the fusion weights online.
    weights = {Layer.DETECTOR: 0.35, Layer.BASELINE: 0.15, Layer.GRAPH: 0.25, Layer.MODEL: 0.25}
    return FeedbackResult(case_id=case_id, status=feedback.verdict, weights_before=weights, weights_after=weights, requeued=0)


@app.get("/eval")
def get_eval() -> EvalReport:
    return fixtures.eval_report()


@app.websocket("/ws/stream")
async def stream(ws: WebSocket) -> None:
    """Replays the fixture stream in a loop; ripple.stream will push live scored transactions here."""
    await ws.accept()
    try:
        while True:
            for event in fixtures.stream_events():
                await ws.send_json(event)
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
