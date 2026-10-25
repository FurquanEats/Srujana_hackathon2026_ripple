"""Typology detectors and the behavioural baseline.

Each detector takes the transaction and the feature store and returns ripple.schema.Reason objects whose text cites
transaction IDs and whose counterfactual says what would have avoided the flag. Thresholds come from the region pack.
"""

from ripple.detectors import baseline
from ripple.detectors.typologies import DETECTORS, run

__all__ = ["DETECTORS", "baseline", "run"]
