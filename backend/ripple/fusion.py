"""Fusion: a logistic layer over the four layer scores, giving one probability per transaction.

    p = sigmoid(bias + w_detector * detector + w_baseline * baseline + w_graph * graph + w_model * model)

Each layer score is between 0 and 1. The starting weights come from the region pack and can be refitted on labelled
data (`fit`) or nudged online by analyst feedback (`update`).

Corroboration rule: without evidence from a detector or the model, p is capped below the Review tier. The baseline
and graph layers describe context (unusual for this account, near other alerts), so on their own they can reach
Watch and no higher; an unusual but honest customer, or a shopper at a store with a flagged account, stays there.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from ripple.schema import Layer

LAYERS = (Layer.DETECTOR, Layer.BASELINE, Layer.GRAPH, Layer.MODEL)
QUIET = 0.1  # a layer score below this counts as "nothing to say" for the corroboration rule


def _sigmoid(x: float) -> float:
    if x < 0:  # math.exp(-x) overflows once weights drift far enough
        z = math.exp(x)
        return z / (1 + z)
    return 1 / (1 + math.exp(-x))


class Fusion:
    def __init__(self, weights: dict[str, float], baseline_only_cap: float) -> None:
        self.bias = float(weights["bias"])
        self.weights = {layer: float(weights[layer.value]) for layer in LAYERS}
        self.baseline_only_cap = baseline_only_cap

    def probability(self, scores: dict[Layer, float]) -> float:
        x = self.bias + sum(self.weights[layer] * scores.get(layer, 0.0) for layer in LAYERS)
        p = _sigmoid(x)
        evidence = max(scores.get(Layer.DETECTOR, 0.0), scores.get(Layer.MODEL, 0.0))
        if evidence < QUIET:
            p = min(p, self.baseline_only_cap)
        return p

    def snapshot(self) -> dict[Layer, float]:
        return dict(self.weights)

    def update(self, samples: Iterable[tuple[dict[Layer, float], int]], lr: float = 0.5) -> None:
        """One pass of stochastic gradient descent on log-loss, one step per (layer scores, label) sample."""
        for scores, label in samples:
            error = _sigmoid(self.bias + sum(self.weights[l] * scores.get(l, 0.0) for l in LAYERS)) - label
            self.bias -= lr * error
            for layer in LAYERS:
                self.weights[layer] -= lr * error * scores.get(layer, 0.0)

    def fit(self, rows: list[dict[Layer, float]], labels: list[int]) -> None:
        """Refit all weights on labelled data, e.g. layer scores from a time-split replay of IBM AML."""
        from sklearn.linear_model import LogisticRegression

        X = [[r.get(layer, 0.0) for layer in LAYERS] for r in rows]
        model = LogisticRegression(class_weight="balanced", max_iter=1000).fit(X, labels)
        self.bias = float(model.intercept_[0])
        self.weights = {layer: float(w) for layer, w in zip(LAYERS, model.coef_[0])}
