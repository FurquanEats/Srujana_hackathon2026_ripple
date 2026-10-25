"""LightGBM model for the engine's model layer: raw features -> calibrated probability + SHAP reasons.

Trained by ripple.eval.ibm and saved as two files: the booster (LightGBM text format) and a JSON sidecar with the
feature order and the isotonic calibration curve. SHAP values come from LightGBM's own pred_contrib (TreeSHAP), so
the shap package is not needed at serving time.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ripple.models.history import HISTORY_FEATURES, AccountHistory
from ripple.schema import Rail, ShapValue, Transaction

TOP_SHAP = 5
# One-hot payment rail. The model derives these from the transaction itself, so the feature store needs no change.
RAIL_FEATURES = [f"rail_{r.value.lower()}" for r in Rail]


def rail_features(rail: Rail | str) -> dict[str, float]:
    value = rail.value if isinstance(rail, Rail) else str(rail)
    return {f"rail_{r.value.lower()}": float(r.value == value) for r in Rail}


def rail_matrix(rails: np.ndarray) -> np.ndarray:
    """rail_features for a column of rail values, as a float32 matrix whose columns follow RAIL_FEATURES."""
    return np.column_stack([(rails == r.value) for r in Rail]).astype(np.float32)


class LightGBMModel:
    def __init__(self, booster, features: list[str], calib_x: list[float], calib_y: list[float]) -> None:
        self.booster = booster
        self.features = features
        self.calib_x = np.asarray(calib_x, dtype=float)
        self.calib_y = np.asarray(calib_y, dtype=float)
        # Account history is state: it grows with the stream the model scores (see ripple.models.history).
        self.history = AccountHistory() if set(HISTORY_FEATURES) & set(features) else None

    @classmethod
    def load(cls, path: str | Path) -> LightGBMModel:
        import lightgbm as lgb

        path = Path(path)
        meta = json.loads(path.with_suffix(".json").read_text())
        return cls(lgb.Booster(model_file=str(path)), meta["features"], meta["calib_x"], meta["calib_y"])

    def save(self, path: str | Path, extra: dict | None = None) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(path))
        meta = {"features": self.features, "calib_x": self.calib_x.tolist(), "calib_y": self.calib_y.tolist()}
        path.with_suffix(".json").write_text(json.dumps(meta | (extra or {}), indent=1))

    def calibrate(self, raw: np.ndarray) -> np.ndarray:
        return np.interp(raw, self.calib_x, self.calib_y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Calibrated probabilities for a feature matrix whose columns follow self.features."""
        return self.calibrate(self.booster.predict(X))

    def observe(self, txn: Transaction) -> None:
        """Adds a payment the engine does not score (a transfer to the same account) to the account history."""
        if self.history is not None:
            self.history.update(txn)

    def score(self, txn: Transaction, features: dict[str, float]) -> tuple[float, list[ShapValue]]:
        features = features | rail_features(txn.rail)
        if self.history is not None:
            features = features | self.history.observe(txn)
        x = np.array([[features.get(name, 0.0) for name in self.features]], dtype=float)
        p = float(self.predict(x)[0])
        contrib = self.booster.predict(x, pred_contrib=True)[0][:-1]  # last column is the expected value
        top = np.argsort(-np.abs(contrib))[:TOP_SHAP]
        return p, [ShapValue(feature=self.features[i], value=float(x[0, i]), contribution=round(float(contrib[i]), 4))
                   for i in top]
