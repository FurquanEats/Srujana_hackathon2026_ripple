"""FastAPI entrypoint: REST routes for cases, feedback and evaluation, transaction ingest, and the /ws/stream WebSocket.

RIPPLE_SOURCE=engine runs the live engine. RIPPLE_DATA is replayed at RIPPLE_SPEED seconds of data per real second:
a CSV or Parquet file, or "sim:india" for a freshly simulated legitimate month whose scam scenarios are injected live
with POST /inject/{kind}; its first RIPPLE_HISTORY_DAYS (default 20) are scored at full speed as account history. POST /ingest accepts more transactions at any time, and POST /trace follows a victim's money.
RIPPLE_SOURCE=fixtures (the default) serves the sample responses in /fixtures.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ripple import feedback, fixtures, interdiction, trace
from ripple.cases import queue_order
from ripple.engine import Engine
from ripple.schema import (
    CaseDetail,
    CaseSummary,
    EvalReport,
    Feedback,
    FeedbackResult,
    InjectResult,
    InterdictionPlan,
    Layer,
    LearnedPattern,
    LearnRequest,
    MotifRule,
    ScoredTransaction,
    TraceRequest,
    Transaction,
)
from ripple.stream import EventBus, Feed, ingest, load_transactions, replay_feed


def create_app(source: str | None = None, data: str | None = None, speed: float | None = None) -> FastAPI:
    source = source or os.environ.get("RIPPLE_SOURCE", "fixtures")
    data = data if data is not None else os.environ.get("RIPPLE_DATA")
    speed = speed if speed is not None else float(os.environ.get("RIPPLE_SPEED", "60"))
    live = source == "engine"
    engine = Engine(os.environ.get("RIPPLE_PACK", "india")) if live else None
    bus = EventBus()
    feed = Feed()
    world = None
    fast_until = None
    if engine is not None and data:
        if data.startswith("sim:"):
            from ripple.sim.india import START, World

            world = World()
            world.simulate()
            feed.add(row.txn for row in world.sorted_rows())
            fast_until = START + timedelta(days=float(os.environ.get("RIPPLE_HISTORY_DAYS", "20")))
        else:
            feed.add(load_transactions(data))

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(replay_feed(engine, bus, feed, speed, fast_until=fast_until)) if engine else None
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

    @app.get("/cases/{case_id}/interdiction")
    def get_interdiction(case_id: str) -> InterdictionPlan:
        """Where the traced money sits now, and the freeze set that recovers the most of it."""
        case = engine.detail(case_id) if engine else fixtures.case_detail(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
        if engine is None:
            return interdiction.plan(case)
        evidence = interdiction.plan(case)  # first pass: which accounts hold traced money
        holders = {h.account_id for h in evidence.holdings}
        trail = [t for t in case.timeline if t.dst_account in holders or t.src_account in holders]
        return interdiction.plan(case, onward=trace.onward(engine, trail))

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

    @app.get("/consortium")
    def get_consortium() -> dict:
        """Consortium uplift on IBM AML from scripts/consortium_eval.py, or 404 until it has been run."""
        path = Path(os.environ.get("RIPPLE_CONSORTIUM", Path(__file__).resolve().parents[3] / "data" / "consortium.json"))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="run scripts/consortium_eval.py first")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/redteam")
    def get_redteam() -> dict:
        """Red-team results from scripts/redteam.py: the latest run, and the run before the last fixes if kept."""
        data_dir = Path(__file__).resolve().parents[3] / "data"
        latest = data_dir / "redteam.json"
        if not latest.is_file():
            raise HTTPException(status_code=404, detail="run scripts/redteam.py first")
        before = data_dir / "redteam_before.json"
        return {"latest": json.loads(latest.read_text(encoding="utf-8")),
                "before": json.loads(before.read_text(encoding="utf-8")) if before.is_file() else None}

    @app.post("/ingest")
    def post_ingest(txns: list[Transaction]) -> list[ScoredTransaction]:
        """Scores transactions in the order given (for example from the simulator's inject buttons)."""
        if engine is None:
            raise HTTPException(status_code=409, detail="ingest needs RIPPLE_SOURCE=engine")
        return [ingest(engine, bus, t).txn for t in sorted(txns, key=lambda t: t.ts)]

    @app.post("/inject/{kind}")
    def post_inject(kind: str) -> InjectResult:
        """Adds a simulated scenario (mule_ring, scam_fanout, sim_swap_takeover, cash_structuring, diwali_spike,
        digital_arrest) at the stream's current time; it flows through the engine like any other traffic."""
        if engine is None or world is None:
            raise HTTPException(status_code=409, detail="inject needs RIPPLE_SOURCE=engine and RIPPLE_DATA=sim:india")
        from ripple.sim.india import INJECTORS

        if kind not in INJECTORS:
            raise HTTPException(status_code=404, detail=f"unknown scenario {kind}; choose from {INJECTORS}")
        at = (engine.store.now or datetime.now()) + timedelta(minutes=2)
        before = len(world.rows)
        txns = world.inject(kind, at)
        feed.add(txns)
        victim = next((row for row in world.rows[before:] if row.victim_account), None)
        return InjectResult(kind=kind, at=at, txn_ids=[t.txn_id for t in txns],
                            victim_account=victim.victim_account if victim else None,
                            victim_paid_at=victim.txn.ts if victim else None)

    @app.post("/trace")
    def post_trace(report: TraceRequest) -> InterdictionPlan:
        """Follows a victim's money forward from the reported time and returns where it sits and what to freeze."""
        if engine is None:
            raise HTTPException(status_code=409, detail="trace needs RIPPLE_SOURCE=engine")
        from_ts = report.from_ts or ((engine.store.now or datetime.now()) - timedelta(hours=24))
        result = trace.trace(engine, report.account, from_ts.replace(tzinfo=None), report.amount)
        if result is None:
            raise HTTPException(status_code=404, detail=f"no payments from {report.account} after {from_ts}")
        return result

    def pattern(motif) -> LearnedPattern:
        return LearnedPattern(
            motif_id=motif.motif_id, name=motif.name, learned_from=motif.learned_from, learned_at=motif.learned_at,
            rules=[MotifRule(feature=c.feature, text=c.describe(), low=c.lo, high=c.hi, background_share=c.background_share)
                   for c in motif.constraints],
            steps=motif.steps, example_txn_ids=motif.example_txn_ids, background_events=motif.background_events,
            background_days=motif.background_days, background_matches=motif.background_matches,
            false_alarms_per_day=round(motif.false_alarms_per_day, 3), lead_hours=motif.lead_hours,
            deployed=motif.deployed, hits=len(motif.hits), recent_hits=motif.hits[-10:],
        )

    def motif_or_404(motif_id: str):
        if engine is None or motif_id not in engine.motifs.motifs:
            raise HTTPException(status_code=404, detail=f"unknown pattern: {motif_id}")
        return engine.motifs.motifs[motif_id]

    @app.get("/motifs")
    def list_motifs() -> list[LearnedPattern]:
        """Patterns learned from confirmed trails, newest first."""
        return [pattern(m) for m in reversed(engine.motifs.motifs.values())] if engine else []

    @app.post("/motifs/learn")
    def learn_motif(request: LearnRequest) -> LearnedPattern:
        """Learns a pattern from one confirmed trail: a case's money trail, or the trace of a victim's report. The
        pattern is checked against the bank's last 30 days of traffic and returned undeployed for the officer to read."""
        if engine is None:
            raise HTTPException(status_code=409, detail="learning needs RIPPLE_SOURCE=engine")
        if request.case_id:
            case = engine.detail(request.case_id)
            if case is None:
                raise HTTPException(status_code=404, detail=f"unknown case: {request.case_id}")
            trail, source = interdiction.plan(case), f"case {request.case_id}"
        elif request.account:
            from_ts = request.from_ts or ((engine.store.now or datetime.now()) - timedelta(hours=24))
            trail = trace.trace(engine, request.account, from_ts.replace(tzinfo=None), request.amount)
            if trail is None:
                raise HTTPException(status_code=404, detail=f"no payments from {request.account} after {from_ts}")
            source = f"the trace of {request.account}'s report"
        else:
            raise HTTPException(status_code=422, detail="give a case_id, or the victim's account to trace")
        try:
            motif = engine.motifs.learn({e.txn_id for e in trail.edges}, source, request.name)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err
        return pattern(motif)

    @app.post("/motifs/{motif_id}/deploy")
    def deploy_motif(motif_id: str) -> LearnedPattern:
        """Puts a learned pattern live: from the next payment on, a match is detector evidence like any typology."""
        motif = motif_or_404(motif_id)
        motif.deployed = True
        return pattern(motif)

    @app.post("/motifs/{motif_id}/retire")
    def retire_motif(motif_id: str) -> LearnedPattern:
        motif = motif_or_404(motif_id)
        motif.deployed = False
        return pattern(motif)

    @app.get("/oneshot")
    def get_oneshot() -> dict:
        """One-shot learning results from scripts/oneshot_eval.py, or 404 until it has been run."""
        path = Path(__file__).resolve().parents[3] / "data" / "oneshot.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="run scripts/oneshot_eval.py first")
        return json.loads(path.read_text(encoding="utf-8"))

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
