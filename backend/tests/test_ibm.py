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


RAW_CSV = """Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering
2022/09/01 00:20,010,8000EBD30,010,8000EBD30,3697.34,US Dollar,3697.34,US Dollar,Reinvestment,0
2022/09/01 00:05,021174,800737690,012,80011F990,2848.96,Euro,2848.96,Euro,ACH,1
2022/09/01 01:00,001,A1,002,B1,110.00,US Dollar,100.00,Euro,Wire,0
2022/09/01 02:00,001,A1,003,C1,100.00,US Dollar,50.00,UK Pound,Wire,0
2022/09/01 03:00,001,A1,003,C1,0.00,US Dollar,0.00,US Dollar,Cash,0
"""

PATTERNS = """BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 16-degree Fan-Out
2022/09/01 00:05,021174,800737690,012,80011F990,2848.96,Euro,2848.96,Euro,ACH,1
END LAUNDERING ATTEMPT - FAN-OUT
"""


def test_ibm_loader_maps_rows_converts_to_usd_and_tags_patterns(tmp_path):
    from ripple.data import ibm
    from ripple.stream.replay import load_transactions

    (tmp_path / "t.csv").write_text(RAW_CSV)
    (tmp_path / "p.txt").write_text(PATTERNS)
    raw = ibm.read_raw(tmp_path / "t.csv")
    rates = ibm.usd_rates(raw)
    assert rates["UK Pound"] == 2.0 and rates["Euro"] == 1.1  # median of received USD over paid

    out = ibm.transform(raw, ibm.read_patterns(tmp_path / "p.txt"), rates)
    assert len(out) == 4  # zero amount dropped
    assert list(out["txn_id"]) == ["ibm-1", "ibm-0", "ibm-2", "ibm-3"]  # sorted by time, IDs keep CSV row order
    first = out.iloc[0]
    assert first["src_account"] == "021174:800737690" and first["rail"] == "ACH"
    assert first["pattern"] == "fan_out" and first["is_laundering"] == 1
    assert out.iloc[3]["amount"] == 100.0 and out.iloc[3]["orig_currency"] == "UK Pound"

    out.to_csv(tmp_path / "out.csv", index=False)
    txns = load_transactions(tmp_path / "out.csv")  # label columns are ignored by Transaction
    assert txns[1].rail == Rail.REINVESTMENT and txns[1].src_account == txns[1].dst_account
