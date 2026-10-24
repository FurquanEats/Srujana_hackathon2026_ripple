"""Typology detectors: pass_through, fan_in_out, fan_out_burst, scatter_gather, temporal_cycle, cash_structuring, device_takeover.

Each detector takes the transaction and the feature store and returns ripple.schema.Reason objects whose text cites
transaction IDs and whose counterfactual says what would have avoided the flag. Thresholds come from the region pack."""
