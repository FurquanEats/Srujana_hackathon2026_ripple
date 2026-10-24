"""Graph layer: a rolling 7-day payment graph with Louvain communities and PageRank.

Communities and PageRank are recomputed every `recompute_every` transactions rather than on every event, because
they are global. Scores between recomputes use the last result. An account scores high when its community holds
several alerted accounts, or when it sits within two hops of an account in a confirmed case.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

import networkx as nx

from ripple.fmt import names
from ripple.schema import Layer, Rail, Reason, Transaction

WINDOW = timedelta(days=7)
MIN_COMMUNITY, MAX_COMMUNITY = 3, 60


@dataclass(frozen=True)
class _Edge:
    txn_id: str
    ts: datetime
    src: str
    dst: str
    amount: float


class GraphLayer:
    def __init__(self, recompute_every: int = 500, seed: int = 7) -> None:
        self.recompute_every = recompute_every
        self.seed = seed
        self.graph = nx.DiGraph()
        self.edges: deque[_Edge] = deque()
        self.alerted: set[str] = set()
        self.confirmed: set[str] = set()
        self.community_of: dict[str, int] = {}
        self.communities: list[set[str]] = []
        self.pagerank: dict[str, float] = {}
        self._since_recompute = 0

    def add(self, txn: Transaction) -> None:
        if txn.rail == Rail.CASH or txn.src_account == txn.dst_account:
            return
        edge = _Edge(txn.txn_id, txn.ts, txn.src_account, txn.dst_account, txn.amount)
        self.edges.append(edge)
        data = self.graph.get_edge_data(edge.src, edge.dst)
        if data is None:
            self.graph.add_edge(edge.src, edge.dst, weight=edge.amount, txns=[edge.txn_id])
        else:
            data["weight"] += edge.amount
            data["txns"].append(edge.txn_id)
        while self.edges and txn.ts - self.edges[0].ts > WINDOW:
            self._remove(self.edges.popleft())
        self._since_recompute += 1
        if self._since_recompute >= self.recompute_every:
            self.recompute()

    def _remove(self, edge: _Edge) -> None:
        data = self.graph.get_edge_data(edge.src, edge.dst)
        if data is None:
            return
        data["weight"] -= edge.amount
        data["txns"].remove(edge.txn_id)
        if not data["txns"]:
            self.graph.remove_edge(edge.src, edge.dst)
            for node in (edge.src, edge.dst):
                if self.graph.degree(node) == 0:
                    self.graph.remove_node(node)

    def recompute(self) -> None:
        self._since_recompute = 0
        if self.graph.number_of_edges() == 0:
            return
        undirected = self.graph.to_undirected()
        self.communities = [set(c) for c in nx.community.louvain_communities(undirected, weight="weight", seed=self.seed)]
        self.community_of = {a: i for i, c in enumerate(self.communities) for a in c}
        self.pagerank = nx.pagerank(self.graph, weight="weight")

    def mark_alert(self, *accounts: str) -> None:
        self.alerted.update(accounts)

    def mark_confirmed(self, accounts: set[str]) -> None:
        self.confirmed |= accounts

    def account_score(self, account: str) -> tuple[float, Reason | None]:
        community_score, community_reason = self._community(account)
        proximity_score, proximity_reason = self._proximity(account)
        if proximity_score > community_score:
            return proximity_score, proximity_reason
        return community_score, community_reason

    def score(self, txn: Transaction) -> tuple[float, Reason | None]:
        return max((self.account_score(a) for a in (txn.src_account, txn.dst_account)), key=lambda s: s[0])

    def _community(self, account: str) -> tuple[float, Reason | None]:
        idx = self.community_of.get(account)
        if idx is None:
            return 0.0, None
        members = self.communities[idx]
        flagged = members & self.alerted
        if not MIN_COMMUNITY <= len(members) <= MAX_COMMUNITY or len(flagged) < 2:
            return 0.0, None
        share = len(flagged) / len(members)
        strength = min(1.0, 0.4 + share)
        hub = max(members, key=lambda a: self.pagerank.get(a, 0.0))
        txn_ids = [t for u, v, d in self.graph.edges(data=True) if u in flagged and v in flagged for t in d["txns"]][:12]
        return strength, Reason(
            layer=Layer.GRAPH,
            code="community",
            text=f"{names(sorted(flagged)[:6])} sit in one tight group of {len(members)} accounts, {len(flagged)} of them "
            f"with alerts; {hub} has the highest PageRank in it, which marks a collector",
            strength=round(strength, 3),
            txn_ids=txn_ids,
        )

    def _proximity(self, account: str) -> tuple[float, Reason | None]:
        if not self.confirmed or account not in self.graph or account in self.confirmed:
            return 0.0, None
        undirected = self.graph.to_undirected(as_view=True)
        near = nx.single_source_shortest_path_length(undirected, account, cutoff=2)
        hits = sorted((dist, a) for a, dist in near.items() if a in self.confirmed and dist > 0)
        if not hits:
            return 0.0, None
        dist, other = hits[0]
        strength = 0.8 if dist == 1 else 0.5
        return strength, Reason(
            layer=Layer.GRAPH,
            code="proximity",
            text=f"{account} is {dist} hop{'s' if dist > 1 else ''} from {other}, which is in a confirmed case",
            strength=strength,
            txn_ids=[],
        )

    def features(self, account: str) -> dict[str, float]:
        idx = self.community_of.get(account)
        return {
            "pagerank": self.pagerank.get(account, 0.0) * max(1, len(self.pagerank)),  # 1.0 = average account
            "community_size": float(len(self.communities[idx])) if idx is not None else 0.0,
            "degree": float(self.graph.degree(account)) if account in self.graph else 0.0,
        }
