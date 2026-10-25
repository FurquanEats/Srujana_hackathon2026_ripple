"""The scoring engine: one call per transaction runs every layer, fuses them and updates cases.

    store.update -> detectors | baseline | graph | model -> fusion -> alert? -> case engine

A transfer from an account to itself (IBM's "Reinvestment") is internal bookkeeping, not a payment between parties,
so it is passed through unscored.

The ML model is optional and plugs in through the `Model` protocol. `on_features` lets a training job capture the
exact feature rows the live engine sees, so training and serving never drift apart.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ripple import detectors
from ripple.cases import Case, CaseEngine
from ripple.features import FeatureStore, baseline, feature_vector
from ripple.fusion import Fusion
from ripple.graph import GraphLayer
from ripple.motifs import MotifLayer
from ripple.packs import load_pack
from ripple.schema import (
    AccountProfile,
    CaseDetail,
    GraphEdge,
    GraphNode,
    Layer,
    Rail,
    Reason,
    ScoredTransaction,
    ShapValue,
    Transaction,
)

DETECTOR_EVIDENCE = 0.5  # detector score an alert needs before it may flag accounts in the graph layer
LOG_WINDOW = timedelta(days=8)  # covers the longest evidence window (7-day cash structuring)
# A non-alert payment that touches a case account, or an account a case account paid (up to ONWARD_HOPS away), from
# three days before the case's first alert to three days after its last, is kept past LOG_WINDOW. A case's evidence,
# the mules' own money and their later withdrawals then stay the same however old the case is.
CASE_BEFORE = timedelta(hours=72)
CASE_AFTER = timedelta(hours=72)
ONWARD_HOPS = 3
CONTEXT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class _Recent:
    """What the engine keeps about a non-alert transaction: enough to show it as case context, at a fraction of the
    memory of a full ScoredTransaction."""

    txn_id: str
    ts: datetime
    src: str
    dst: str
    amount: float
    currency: str
    rail: Rail
    probability: float

    def scored(self) -> ScoredTransaction:
        return ScoredTransaction(
            txn_id=self.txn_id, ts=self.ts, src_account=self.src, dst_account=self.dst, amount=self.amount,
            currency=self.currency, rail=self.rail, probability=self.probability, confidence=1.0,
            layer_scores={layer: 0.0 for layer in Layer},
        )


class Model(Protocol):
    def score(self, txn: Transaction, features: dict[str, float]) -> tuple[float, list[ShapValue]]: ...


class Engine:
    def __init__(
        self,
        pack_id: str = "india",
        model: Model | None = None,
        on_features: Callable[[Transaction, dict[str, float]], None] | None = None,
    ) -> None:
        self.pack = load_pack(pack_id)
        self.model = model
        self.on_features = on_features
        self.external: Callable[[Transaction], Reason | None] | None = None  # e.g. a consortium hub lookup
        self.store = FeatureStore()
        self.motifs = MotifLayer()  # patterns learned from confirmed trails, see ripple.motifs
        self.motifs.tracker.keep = lambda txn_id: txn_id in self.log or txn_id in self.kept
        self.graph = GraphLayer(self.pack["graph"]["recompute_every"], self.pack["graph"].get("window_days", 7))
        fusion_cfg = self.pack["fusion"]
        self.fusion = Fusion(fusion_cfg["weights"], fusion_cfg["baseline_only_cap"])
        self.dismiss_for = timedelta(days=fusion_cfg["dismiss_days"])
        self.alert_at = self.pack["tiers"]["alert"]
        self.warmup = timedelta(hours=self.pack.get("warmup_hours", 0))
        self.stream_start: datetime | None = None
        self.dismissed: dict[tuple[str, str], datetime] = {}  # account pair -> suppressed until
        self.log: dict[str, ScoredTransaction] = {}  # every alert, in full
        self.recent: dict[str, _Recent] = {}  # every non-alert transaction within LOG_WINDOW, compact
        self.kept: dict[str, _Recent] = {}  # older non-alert transactions that belong to a case's story
        self._onward: dict[str, tuple[str, int]] = {}  # account paid by a case's money -> (case id, hops from the case)
        self.cases = CaseEngine(self.pack["tiers"], amount_of=self._amount_of)
        self._recent_order: deque[tuple[datetime, str]] = deque()
        self.shap: dict[str, list[ShapValue]] = {}
        self.processed = 0
        self.alerts = 0
        self._latency_ms: deque[float] = deque(maxlen=2000)
        self._started = time.perf_counter()

    def process(self, txn: Transaction) -> tuple[ScoredTransaction, Case | None]:
        began = time.perf_counter()
        if self.stream_start is None:
            self.stream_start = txn.ts
        if txn.src_account == txn.dst_account:
            self.processed += 1
            return ScoredTransaction(
                **txn.model_dump(), probability=0.0, confidence=1.0, layer_scores={layer: 0.0 for layer in Layer}
            ), None
        src, dst = self.store.update(txn)

        hits = detectors.run(txn, self.store, src, dst, self.pack) + self.motifs.observe(txn)
        detector_score = 1.0
        for r in hits:
            detector_score *= 1 - r.strength
        detector_score = 1 - detector_score
        baseline_score, baseline_reasons, has_history = detectors.baseline.score(txn, src, dst)

        self.graph.add(txn)
        graph_score, graph_reason = self.graph.score(txn)
        if self.external is not None and (shared := self.external(txn)) is not None and shared.strength > graph_score:
            graph_score, graph_reason = shared.strength, shared

        features = feature_vector(txn, src, dst) | {f"src_{k}": v for k, v in self.graph.features(txn.src_account).items()} | {
            f"dst_{k}": v for k, v in self.graph.features(txn.dst_account).items()
        }
        if self.on_features:
            self.on_features(txn, features)
        model_score, shap = self.model.score(txn, features) if self.model else (0.0, [])

        layers = {Layer.DETECTOR: detector_score, Layer.BASELINE: baseline_score, Layer.GRAPH: graph_score, Layer.MODEL: model_score}
        p = self.fusion.probability(layers)
        until = self.dismissed.get((txn.src_account, txn.dst_account))
        if until and txn.ts < until:
            p = min(p, self.alert_at - 0.01)

        reasons: list[Reason] = sorted(hits + baseline_reasons + ([graph_reason] if graph_reason else []), key=lambda r: -r.strength)
        scored = ScoredTransaction(
            **txn.model_dump(),
            probability=round(p, 4),
            confidence=_confidence(txn, has_history),
            layer_scores={k: round(v, 4) for k, v in layers.items()},
            reasons=reasons,
            is_alert=p >= self.alert_at and not self.warming_up(txn.ts),
        )
        self.store.after_score(txn)
        self._remember(scored)

        case = None
        if scored.is_alert:
            self.alerts += 1
            self.shap[txn.txn_id] = shap
            if detector_score >= DETECTOR_EVIDENCE:
                self.graph.mark_alert(txn.ts, txn.src_account, txn.dst_account)
            case = self.cases.add(scored)
            self._onward.setdefault(scored.dst_account, (case.case_id, 1))
        self.processed += 1
        self._latency_ms.append((time.perf_counter() - began) * 1000)
        return scored, case

    def _remember(self, scored: ScoredTransaction) -> None:
        if scored.is_alert:
            self.log[scored.txn_id] = scored
        else:
            self.recent[scored.txn_id] = _Recent(
                scored.txn_id, scored.ts, scored.src_account, scored.dst_account, scored.amount, scored.currency,
                scored.rail, scored.probability,
            )
            self._recent_order.append((scored.ts, scored.txn_id))
        while self._recent_order and scored.ts - self._recent_order[0][0] > LOG_WINDOW:
            old = self.recent.pop(self._recent_order.popleft()[1], None)
            if old is not None and self._in_case(old):
                self.kept[old.txn_id] = old

    def _case_of(self, account: str, ts: datetime) -> tuple[str, int] | None:
        """The case whose story this account belongs to at this time, and how many hops it is from the case."""
        hit = self.cases._latest.get(account)
        for case_id, hops in ((hit[0], 0) if hit else (None, 0), self._onward.get(account, (None, 0))):
            case = self.cases.get(case_id) if case_id else None
            if case and case.alerts[0].ts - CASE_BEFORE <= ts <= case.alerts[-1].ts + CASE_AFTER:
                return case.case_id, hops
        return None

    def _in_case(self, t: _Recent) -> bool:
        for account in (t.src, t.dst):
            found = self._case_of(account, t.ts)
            if found is None:
                continue
            state = self.store.get(t.dst)
            shop = state is not None and len(state.senders) > 20
            if account == t.src and found[1] < ONWARD_HOPS and not shop:
                self._onward.setdefault(t.dst, (found[0], found[1] + 1))
            return True
        return False

    def payments(self, account: str) -> list[ScoredTransaction]:
        """Every payment into or out of an account that the engine still holds: its rolling window, every alert, and
        the older payments kept for cases. Oldest first."""
        found: dict[str, ScoredTransaction] = {}
        state = self.store.get(account)
        if state is not None:
            for edge in state.incoming + state.outgoing:
                if (txn := self.lookup(edge.txn_id)) is not None:
                    found[txn.txn_id] = txn
        for t in self.log.values():
            if account in (t.src_account, t.dst_account):
                found[t.txn_id] = t
        for t in self.kept.values():
            if account in (t.src, t.dst):
                found[t.txn_id] = t.scored()
        return sorted(found.values(), key=lambda t: t.ts)

    def _amount_of(self, txn_id: str) -> float:
        hit = self.log.get(txn_id) or self.recent.get(txn_id) or self.kept.get(txn_id)
        return hit.amount if hit else 0.0

    def lookup(self, txn_id: str) -> ScoredTransaction | None:
        if txn_id in self.log:
            return self.log[txn_id]
        hit = self.recent.get(txn_id) or self.kept.get(txn_id)
        return hit.scored() if hit else None

    def warming_up(self, ts: datetime) -> bool:
        """While the engine has seen less than `warmup_hours` of data, every payee and sender looks new and every
        baseline is empty, so it scores transactions but raises no alerts."""
        return self.stream_start is not None and ts - self.stream_start < self.warmup

    def stats(self) -> dict[str, float]:
        elapsed = max(time.perf_counter() - self._started, 1e-9)
        lat = sorted(self._latency_ms)
        return {
            "processed": float(self.processed),
            "alerts": float(self.alerts),
            "open_cases": float(sum(1 for c in self.cases.cases.values() if c.status == "open")),
            "tps": round(self.processed / elapsed, 1),
            "p95_latency_ms": round(lat[int(0.95 * (len(lat) - 1))], 2) if lat else 0.0,
            "warming_up": float(self.store.now is not None and self.warming_up(self.store.now)),
        }

    def detail(self, case_id: str) -> CaseDetail | None:
        case = self.cases.get(case_id)
        if case is None:
            return None
        summary = self.cases.summary(case)
        accounts = case.accounts
        first_alert = case.alerts[0].ts

        timeline = {t.txn_id: t for t in case.alerts}
        for account in accounts:
            state = self.store.get(account)
            if state is None:
                continue
            for edge in state.incoming + state.outgoing + state.cash_deposits:
                if first_alert - CONTEXT_WINDOW <= edge.ts <= case.alerts[-1].ts and edge.txn_id not in timeline:
                    found = self.lookup(edge.txn_id)
                    if found is not None:
                        timeline[edge.txn_id] = found
        for alert in case.alerts:  # evidence the reasons cite, even when it is older than the context window
            for reason in alert.reasons:
                for txn_id in reason.txn_ids:
                    if txn_id not in timeline and (found := self.lookup(txn_id)) is not None:
                        timeline[txn_id] = found
        ordered = sorted(timeline.values(), key=lambda t: t.ts)[:300]

        best: dict[str, Reason] = {}
        for t in case.alerts:
            for r in t.reasons:
                if r.code not in best or r.strength > best[r.code].strength:
                    best[r.code] = r
        top = max(case.alerts, key=lambda t: t.probability)

        risk: dict[str, float] = {}
        sends, gets = set(), set()
        for t in ordered:
            for a in (t.src_account, t.dst_account):
                risk[a] = max(risk.get(a, 0.0), t.probability)
            sends.add(t.src_account)
            gets.add(t.dst_account)
        nodes = [GraphNode(id=a, label=a, role=_role(a, accounts, sends, gets), risk=round(r, 4)) for a, r in sorted(risk.items())]
        edges = [GraphEdge(txn_id=t.txn_id, source=t.src_account, target=t.dst_account, amount=t.amount, ts=t.ts) for t in ordered]

        return CaseDetail(
            **summary.model_dump(),
            reasons=sorted(best.values(), key=lambda r: -r.strength),
            shap=self.shap.get(top.txn_id, []),
            nodes=nodes,
            edges=edges,
            timeline=ordered,
            profiles=[p for p in (self._profile(a) for a in sorted(accounts)) if p],
        )

    def _profile(self, account: str) -> AccountProfile | None:
        state = self.store.get(account)
        if state is None:
            return None
        b = baseline(state, skip_last=False)
        return AccountProfile(
            account_id=account,
            opened_days_ago=(self.store.now - state.first_seen).days if self.store.now else None,
            median_amount_30d=round(b.median, 2) if b else None,
            txns_30d=len(state.out_history),
            devices=sorted(state.devices),
        )


def _confidence(txn: Transaction, has_history: bool) -> float:
    """Share of the evidence the layers rely on that was actually present. Missing data lowers it, never risk."""
    c = 1.0
    if txn.device_id is None:
        c -= 0.15
    if txn.location is None:
        c -= 0.1
    if not has_history:
        c -= 0.2
    return round(max(c, 0.3), 2)


def _role(account: str, case_accounts: set[str], sends: set[str], gets: set[str]) -> str:
    if account not in case_accounts:
        return "other"
    if account in sends and account in gets:
        return "mule"
    return "collector" if account in gets else "source"
