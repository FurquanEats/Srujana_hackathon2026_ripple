"""Replays a transaction file through the engine at a chosen speed and publishes every result on the bus."""

from __future__ import annotations

import asyncio
import heapq
import logging
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from ripple.engine import Engine
from ripple.schema import StreamEvent, Transaction
from ripple.stream.bus import EventBus

log = logging.getLogger(__name__)

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


class Feed:
    """Transactions waiting to be replayed, kept in time order. Injected scenarios are inserted at their own times,
    so the engine always sees one ordered stream even when a demo button adds transactions mid-replay."""

    def __init__(self, txns: Iterable[Transaction] = ()) -> None:
        self._items: list[tuple] = []
        self._seq = 0
        self.add(txns)

    def add(self, txns: Iterable[Transaction]) -> None:
        for txn in txns:
            self._seq += 1
            heapq.heappush(self._items, (txn.ts, self._seq, txn))

    def pop(self) -> Transaction | None:
        return heapq.heappop(self._items)[2] if self._items else None

    def __len__(self) -> int:
        return len(self._items)


async def replay_feed(engine: Engine, bus: EventBus, feed: Feed, speed: float = 60.0, idle: float = 0.25,
                      fast_until: datetime | None = None) -> None:
    """Replays the feed and then keeps waiting for injected transactions, so the stream stays live for the demo.
    Transactions before `fast_until` are scored as fast as possible, so the engine starts with the account history a
    real bank would already hold, and only the rest plays at `speed`."""
    previous = None
    last_stats = time.monotonic()
    while True:
        txn = feed.pop()
        if txn is None:
            await asyncio.sleep(idle)
        else:
            fast = fast_until is not None and txn.ts < fast_until
            if previous is not None and speed > 0 and not fast:
                gap = (txn.ts - previous).total_seconds() / speed
                if gap > 0:
                    await asyncio.sleep(min(gap, MAX_SLEEP))
            previous = max(previous, txn.ts) if previous else txn.ts
            try:
                if fast:
                    engine.process(txn)  # history: scored and stored, not pushed to screens
                else:
                    ingest(engine, bus, txn)
            except Exception:  # one bad payment must not end the stream for every screen
                log.exception("could not score %s; skipped", txn.txn_id)
            if not fast or len(feed) % 500 == 0:
                await asyncio.sleep(0)
        if time.monotonic() - last_stats >= STATS_EVERY:
            stats = engine.stats() | {"queued": float(len(feed))}
            bus.publish(StreamEvent(type="stats", stats=stats).model_dump(mode="json", exclude_none=True))
            last_stats = time.monotonic()
