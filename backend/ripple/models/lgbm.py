"""LightGBM model for the engine's model layer: raw features -> calibrated probability + SHAP reasons.

Trained by ripple.eval.ibm and saved as two files: the booster (LightGBM text format) and a JSON sidecar with the
feature order and the isotonic calibration curve. SHAP values come from LightGBM's own pred_contrib (TreeSHAP), so
the shap package is not needed at serving time.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ripple.schema import ShapValue, Transaction

TOP_SHAP = 5


class LightGBMModel:
    def __init__(self, booster, features: list[str], calib_x: list[float], calib_y: list[float]) -> None:
        self.booster = booster
        self.features = features
        self.calib_x = np.asarray(calib_x, dtype=float)
        self.calib_y = np.asarray(calib_y, dtype=float)

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

    def score(self, txn: Transaction, features: dict[str, float]) -> tuple[float, list[ShapValue]]:
        x = np.array([[features.get(name, 0.0) for name in self.features]], dtype=float)
        p = float(self.predict(x)[0])
        contrib = self.booster.predict(x, pred_contrib=True)[0][:-1]  # last column is the expected value
        top = np.argsort(-np.abs(contrib))[:TOP_SHAP]
        return p, [ShapValue(feature=self.features[i], value=float(x[0, i]), contribution=round(float(contrib[i]), 4))
                   for i in top]
