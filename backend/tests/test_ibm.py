"""IBM AML style data: its payment formats map onto the schema and run through the engine in the USD pack."""

from datetime import datetime, timedelta

from ripple.engine import Engine
from ripple.schema import IBM_PAYMENT_FORMATS, Rail, Transaction


def test_every_ibm_payment_format_maps_to_a_rail():
    for fmt in ("ACH", "Wire", "Cheque", "Credit Card", "Cash", "Bitcoin", "Reinvestment"):
        assert isinstance(IBM_PAYMENT_FORMATS[fmt], Rail)


def test_ibm_style_fan_in_then_out_is_flagged_in_dollars():
    t0 = datetime(2022, 9, 1, 0, 0)
    txns = [
        Transaction(txn_id=f"I{i}", ts=t0 + timedelta(minutes=20 * i), src_account=f"0011_{i:04d}",
                    dst_account="0070_HUB", amount=3000 + 100 * i, currency="USD", rail=Rail.ACH)
        for i in range(6)
    ]
    txns.append(Transaction(txn_id="I_OUT", ts=t0 + timedelta(minutes=130), src_account="0070_HUB",
                            dst_account="0099_OUT", amount=17000, currency="USD", rail=Rail.WIRE))
    engine = Engine("ibm_aml")
    scored = [engine.process(t)[0] for t in txns][-1]
    reasons = {r.code: r for r in scored.reasons}
    assert "fan_in_out" in reasons
    assert "USD" in reasons["fan_in_out"].text and "Rs" not in reasons["fan_in_out"].text
    assert scored.device_id is None and scored.confidence < 1  # IBM has no device or location data


def test_ibm_cash_does_not_raise_indian_ctr_flag():
    t0 = datetime(2022, 9, 1)
    engine = Engine("ibm_aml")
    for i in range(5):
        scored, _ = engine.process(Transaction(txn_id=f"C{i}", ts=t0 + timedelta(hours=i), src_account="0001_A",
                                               dst_account="0002_B", amount=300000, currency="USD", rail=Rail.CASH))
        assert "ctr_reportable" not in {r.code for r in scored.reasons}
