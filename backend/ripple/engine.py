"""The scoring engine: one call per transaction runs every layer, fuses them and updates cases.

    store.update -> detectors | baseline | graph | model -> fusion -> alert? -> case engine

The ML model is optional and plugs in through the `Model` protocol. `on_features` lets a training job capture the
exact feature rows the live engine sees, so training and serving never drift apart.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from ripple import detectors
from ripple.cases import Case, CaseEngine
from ripple.features import FeatureStore, baseline, feature_vector
from ripple.fusion import Fusion
from ripple.graph import GraphLayer
from ripple.packs import load_pack
from ripple.schema import (
    AccountProfile,
    CaseDetail,
    GraphEdge,
    GraphNode,
    Layer,
    Reason,
    ScoredTransaction,
    ShapValue,
    Transaction,
)

LOG_WINDOW = timedelta(days=8)  # covers the longest evidence window (7-day cash structuring)
CONTEXT_WINDOW = timedelta(hours=24)


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
        self.store = FeatureStore()
        self.graph = GraphLayer(recompute_every=self.pack["graph"]["recompute_every"])
        fusion_cfg = self.pack["fusion"]
        self.fusion = Fusion(fusion_cfg["weights"], fusion_cfg["baseline_only_cap"])
        self.dismiss_for = timedelta(days=fusion_cfg["dismiss_days"])
        self.alert_at = self.pack["tiers"]["alert"]
        self.dismissed: dict[tuple[str, str], datetime] = {}  # account pair -> suppressed until
        self.log: dict[str, ScoredTransaction] = {}
        self.cases = CaseEngine(self.pack["tiers"], amount_of=lambda i: self.log[i].amount if i in self.log else 0.0)
        self._log_order: deque[tuple[datetime, str]] = deque()
        self.shap: dict[str, list[ShapValue]] = {}
        self.processed = 0
        self.alerts = 0
        self._latency_ms: deque[float] = deque(maxlen=2000)
        self._started = time.perf_counter()

    def process(self, txn: Transaction) -> tuple[ScoredTransaction, Case | None]:
        began = time.perf_counter()
        src, dst = self.store.update(txn)

        hits = detectors.run(txn, self.store, src, dst, self.pack)
        detector_score = 1.0
        for r in hits:
            detector_score *= 1 - r.strength
        detector_score = 1 - detector_score
        baseline_score, baseline_reasons, has_history = detectors.baseline.score(txn, src, dst)

        self.graph.add(txn)
        graph_score, graph_reason = self.graph.score(txn)

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
            is_alert=p >= self.alert_at,
        )
        self.store.after_score(txn)
        self._remember(scored)

        case = None
        if scored.is_alert:
            self.alerts += 1
            self.shap[txn.txn_id] = shap
            self.graph.mark_alert(txn.src_account, txn.dst_account)
            case = self.cases.add(scored)
        self.processed += 1
        self._latency_ms.append((time.perf_counter() - began) * 1000)
        return scored, case

    def _remember(self, scored: ScoredTransaction) -> None:
        self.log[scored.txn_id] = scored
        self._log_order.append((scored.ts, scored.txn_id))
        while self._log_order and scored.ts - self._log_order[0][0] > LOG_WINDOW:
            _, old = self._log_order.popleft()
            if self.log.get(old) is not None and not self.log[old].is_alert:
                del self.log[old]

    def stats(self) -> dict[str, float]:
        elapsed = max(time.perf_counter() - self._started, 1e-9)
        lat = sorted(self._latency_ms)
        return {
            "processed": float(self.processed),
            "alerts": float(self.alerts),
            "open_cases": float(sum(1 for c in self.cases.cases.values() if c.status == "open")),
            "tps": round(self.processed / elapsed, 1),
            "p95_latency_ms": round(lat[int(0.95 * (len(lat) - 1))], 2) if lat else 0.0,
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
            for edge in list(state.incoming) + list(state.outgoing) + list(state.cash_deposits):
                if first_alert - CONTEXT_WINDOW <= edge.ts <= case.alerts[-1].ts and edge.txn_id in self.log:
                    timeline.setdefault(edge.txn_id, self.log[edge.txn_id])
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
