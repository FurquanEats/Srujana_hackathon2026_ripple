"""FastAPI entrypoint: REST routes for cases, feedback and evaluation, transaction ingest, and the /ws/stream WebSocket.

RIPPLE_SOURCE=engine runs the live engine; RIPPLE_DATA (CSV or Parquet) is then replayed at RIPPLE_SPEED seconds of
data per real second, and POST /ingest accepts more transactions at any time. RIPPLE_SOURCE=fixtures (the default)
serves the sample responses in /fixtures.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ripple import feedback, fixtures
from ripple.cases import queue_order
from ripple.engine import Engine
from ripple.schema import CaseDetail, CaseSummary, EvalReport, Feedback, FeedbackResult, Layer, ScoredTransaction, Transaction
from ripple.stream import EventBus, ingest, load_transactions, replay


def create_app(source: str | None = None, data: str | None = None, speed: float | None = None) -> FastAPI:
    source = source or os.environ.get("RIPPLE_SOURCE", "fixtures")
    data = data if data is not None else os.environ.get("RIPPLE_DATA")
    speed = speed if speed is not None else float(os.environ.get("RIPPLE_SPEED", "60"))
    live = source == "engine"
    engine = Engine(os.environ.get("RIPPLE_PACK", "india")) if live else None
    bus = EventBus()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = None
        if engine is not None and data:
            task = asyncio.create_task(replay(engine, bus, load_transactions(data), speed))
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Ripple", version="0.2.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.bus = bus
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("RIPPLE_CORS_ORIGINS", "http://localhost:3000").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "source": source, **({"stats": engine.stats()} if engine else {})}

    @app.get("/cases")
    def list_cases(budget: int = Query(50, ge=1, le=1000), status: str = Query("open")) -> list[CaseSummary]:
        """Cases with the given status, by tier then expected loss, cut to the alert budget. status=all for every case."""
        if engine is None:
            cases = queue_order(fixtures.cases())
        else:
            cases = engine.cases.ranked(None if status == "all" else status)
        return cases[:budget]

    @app.get("/cases/{case_id}")
    def get_case(case_id: str) -> CaseDetail:
        case = engine.detail(case_id) if engine else fixtures.case_detail(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
        return case

    @app.post("/cases/{case_id}/feedback")
    def post_feedback(case_id: str, verdict: Feedback) -> FeedbackResult:
        if engine is None:
            if case_id not in {c.case_id for c in fixtures.cases()}:
                raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
            weights = {Layer.DETECTOR: 6.5, Layer.BASELINE: 4.5, Layer.GRAPH: 3.0, Layer.MODEL: 5.0}
            return FeedbackResult(case_id=case_id, status=verdict.verdict, weights_before=weights, weights_after=weights, requeued=0)
        result = feedback.apply(engine, case_id, verdict.verdict)
        if result is None:
            raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
        return result

    @app.get("/eval")
    def get_eval() -> EvalReport:
        path = Path(os.environ.get("RIPPLE_EVAL", Path(__file__).resolve().parents[3] / "data" / "eval.json"))
        if path.is_file():
            return EvalReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
        return fixtures.eval_report()

    @app.post("/ingest")
    def post_ingest(txns: list[Transaction]) -> list[ScoredTransaction]:
        """Scores transactions in the order given (for example from the simulator's inject buttons)."""
        if engine is None:
            raise HTTPException(status_code=409, detail="ingest needs RIPPLE_SOURCE=engine")
        return [ingest(engine, bus, t).txn for t in sorted(txns, key=lambda t: t.ts)]

    @app.get("/stats")
    def stats() -> dict[str, float]:
        return engine.stats() if engine else {}

    @app.websocket("/ws/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        if engine is None:
            try:
                while True:
                    for event in fixtures.stream_events():
                        await ws.send_json(event)
                        await asyncio.sleep(0.5)
            except WebSocketDisconnect:
                return
        queue = bus.subscribe()
        try:
            while True:
                await ws.send_json(await queue.get())
        except WebSocketDisconnect:
            return
        finally:
            bus.unsubscribe(queue)

    return app


app = create_app()
