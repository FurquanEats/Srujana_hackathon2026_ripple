"""Fusion. Logistic layer over detector, baseline, graph and model scores giving one calibrated probability.

Corroboration rule: a transaction backed only by the baseline layer is capped at Watch. Missing fields lower
confidence, never raise risk."""
