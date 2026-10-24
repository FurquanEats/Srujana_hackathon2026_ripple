"""Graph layer: a rolling payment graph with Louvain communities and PageRank around alerted accounts.

Communities and PageRank are recomputed every `recompute_every` transactions, and only on the neighbourhood of
accounts with alerts inside the graph window (each plus its direct counterparties, newest alerts first, capped at
MAX_NEIGHBOURHOOD nodes).
That is the only place they are used, and computing them on the whole graph does not scale: on IBM AML's 5 million
transactions a full recompute took longer than the 20,000 transactions between recomputes. Scores between recomputes
use the last result. An account scores high when its community holds several alerted accounts, or when it sits
within two hops of an account in a confirmed case.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

import networkx as nx

from ripple.fmt import names
from ripple.schema import Layer, Rail, Reason, Transaction

MIN_COMMUNITY, MAX_COMMUNITY = 3, 60
MIN_FLAGGED, MIN_FLAGGED_SHARE = 3, 0.3  # a community scores only when this many of its members, and this share, are flagged
MERCHANT_SENDERS = 20  # an account paid by more distinct senders than this is treated as a merchant and never flagged
MAX_NEIGHBOURHOOD = 5_000


@dataclass(frozen=True, slots=True)
class _Edge:
    txn_id: str
    ts: datetime
    src: str
    dst: str
    amount: float


class GraphLayer:
    def __init__(self, recompute_every: int = 500, window_days: float = 7, seed: int = 7) -> None:
        self.recompute_every = recompute_every
        self.window = timedelta(days=window_days)
        self.seed = seed
        self.graph = nx.DiGraph()
        self.edges: deque[_Edge] = deque()
        self.alerted: dict[str, datetime] = {}  # account -> time of its latest alert
        self.confirmed: set[str] = set()
        self.community_of: dict[str, int] = {}
        self.communities: list[set[str]] = []
        self.pagerank: dict[str, float] = {}
        self.in_weight: dict[str, float] = {}  # kept incrementally; networkx sums every neighbour on each call
        self.out_weight: dict[str, float] = {}
        self._since_recompute = 0

    def add(self, txn: Transaction) -> None:
        if txn.rail == Rail.CASH or txn.src_account == txn.dst_account:
            return
        edge = _Edge(txn.txn_id, txn.ts, txn.src_account, txn.dst_account, txn.amount)
        self.edges.append(edge)
        self.out_weight[edge.src] = self.out_weight.get(edge.src, 0.0) + edge.amount
        self.in_weight[edge.dst] = self.in_weight.get(edge.dst, 0.0) + edge.amount
        data = self.graph.get_edge_data(edge.src, edge.dst)
        if data is None:
            self.graph.add_edge(edge.src, edge.dst, weight=edge.amount, txns=[edge.txn_id])
        else:
            data["weight"] += edge.amount
            data["txns"].append(edge.txn_id)
        while self.edges and txn.ts - self.edges[0].ts > self.window:
            self._remove(self.edges.popleft())
        self._since_recompute += 1
        if self._since_recompute >= self.recompute_every:
            self.recompute()

    def _remove(self, edge: _Edge) -> None:
        data = self.graph.get_edge_data(edge.src, edge.dst)
        if data is None:
            return
        self.out_weight[edge.src] -= edge.amount
        self.in_weight[edge.dst] -= edge.amount
        data["weight"] -= edge.amount
        data["txns"].remove(edge.txn_id)
        if not data["txns"]:
            self.graph.remove_edge(edge.src, edge.dst)
            for node in (edge.src, edge.dst):
                if self.graph.degree(node) == 0:
                    self.graph.remove_node(node)
                    self.in_weight.pop(node, None)
                    self.out_weight.pop(node, None)

    def recompute(self) -> None:
        self._since_recompute = 0
        now = self.edges[-1].ts if self.edges else None
        self.alerted = {a: ts for a, ts in self.alerted.items() if a in self.graph and now and now - ts <= self.window}
        nodes: set[str] = set()
        for account in sorted(self.alerted, key=self.alerted.get, reverse=True):
            nodes.add(account)
            nodes.update(self.graph.successors(account))
            nodes.update(self.graph.predecessors(account))
            if len(nodes) >= MAX_NEIGHBOURHOOD:
                break
        sub = self.graph.subgraph(nodes)
        if sub.number_of_edges() == 0:
            self.communities, self.community_of, self.pagerank = [], {}, {}
            return
        self.communities = [set(c) for c in nx.community.louvain_communities(sub.to_undirected(), weight="weight", seed=self.seed)]
        self.community_of = {a: i for i, c in enumerate(self.communities) for a in c}
        self.pagerank = nx.pagerank(sub, weight="weight")

    def mark_alert(self, ts: datetime, *accounts: str) -> None:
        """Flags accounts from an alert backed by detector evidence. The engine never calls this for alerts that rest
        on the graph layer itself, so one false alert cannot snowball through a shop's customers. A merchant (paid by
        many distinct senders) is never flagged, because its community is simply its customers."""
        for account in accounts:
            if account in self.graph and self.graph.in_degree(account) > MERCHANT_SENDERS:
                continue
            self.alerted[account] = ts

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
        flagged = members & self.alerted.keys()
        share = len(flagged) / len(members) if members else 0.0
        if not MIN_COMMUNITY <= len(members) <= MAX_COMMUNITY or len(flagged) < MIN_FLAGGED or share < MIN_FLAGGED_SHARE:
            return 0.0, None
        strength = min(1.0, 0.3 + share)
        hub = max(members, key=lambda a: self.pagerank.get(a, 0.0))
        txn_ids = [t for u in flagged for v, d in self.graph.adj.get(u, {}).items() if v in flagged for t in d["txns"]][:12]
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
        """Raw graph features for the ML model. Communities and PageRank are left out on purpose: they are computed
        only around alerts, so they would feed the detectors' own output back into the model."""
        if account not in self.graph:
            return {"in_degree": 0.0, "out_degree": 0.0, "in_weight": 0.0, "out_weight": 0.0}
        return {
            "in_degree": float(self.graph.in_degree(account)),
            "out_degree": float(self.graph.out_degree(account)),
            "in_weight": self.in_weight.get(account, 0.0),
            "out_weight": self.out_weight.get(account, 0.0),
        }
