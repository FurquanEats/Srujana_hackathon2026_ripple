"""Replays a transaction file through the engine at a chosen speed and publishes every result on the bus."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from pathlib import Path

from ripple.engine import Engine
from ripple.schema import StreamEvent, Transaction
from ripple.stream.bus import EventBus

MAX_SLEEP = 1.0  # seconds; long quiet gaps in the data are compressed to this
STATS_EVERY = 1.0  # seconds between stats events


def load_transactions(path: str | Path) -> list[Transaction]:
    """Reads a CSV or Parquet file whose columns follow ripple.schema.Transaction, sorted by time."""
    import pandas as pd

    path = Path(path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    df = df.sort_values("ts")
    df = df.astype(object).where(df.notna(), None)
    return [Transaction.model_validate(row) for row in df.to_dict("records")]


def ingest(engine: Engine, bus: EventBus, txn: Transaction) -> StreamEvent:
    """Scores one transaction and publishes the transaction and, if it is an alert, its case."""
    scored, case = engine.process(txn)
    event = StreamEvent(type="txn", txn=scored)
    bus.publish(event.model_dump(mode="json", exclude_none=True))
    if case is not None:
        summary = engine.cases.summary(case)
        bus.publish(StreamEvent(type="case", case=summary).model_dump(mode="json", exclude_none=True))
    return event


async def replay(engine: Engine, bus: EventBus, txns: Iterable[Transaction], speed: float = 60.0) -> None:
    """Feeds transactions in time order. `speed` is how many seconds of data pass per real second."""
    previous = None
    last_stats = time.monotonic()
    for txn in txns:
        if previous is not None and speed > 0:
            gap = (txn.ts - previous).total_seconds() / speed
            if gap > 0:
                await asyncio.sleep(min(gap, MAX_SLEEP))
        previous = txn.ts
        ingest(engine, bus, txn)
        if time.monotonic() - last_stats >= STATS_EVERY:
            bus.publish(StreamEvent(type="stats", stats=engine.stats()).model_dump(mode="json", exclude_none=True))
            last_stats = time.monotonic()
        await asyncio.sleep(0)  # let WebSocket senders run between events
    bus.publish(StreamEvent(type="stats", stats=engine.stats()).model_dump(mode="json", exclude_none=True))
