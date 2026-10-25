import pytest
from hypothesis import given
from hypothesis import strategies as st

from ripple_core import ids
from ripple_core.money import fmt_inr, rupees, split_pro_rata


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0"),
        (87300, "₹873"),
        (25000000, "₹2,50,000"),
        (4069508, "₹40,695.08"),
        (-150, "-₹1.50"),
        (123456789012, "₹1,23,45,67,890.12"),
    ],
)
def test_fmt_inr_uses_indian_grouping(paise: int, text: str) -> None:
    assert fmt_inr(paise) == text


def test_rupees_parses_and_refuses_fractions_of_a_paisa() -> None:
    assert rupees("2,50,000.50") == 25000050
    assert rupees(873) == 87300
    with pytest.raises(ValueError, match="fraction"):
        rupees("1.001")
    with pytest.raises(ValueError, match="not a rupee"):
        rupees("lots")


@given(
    st.integers(0, 10**12),
    st.dictionaries(st.text(min_size=1, max_size=3), st.integers(0, 10**9), min_size=1),
)
def test_split_pro_rata_is_exact_and_fair(total: int, weights: dict[str, int]) -> None:
    if sum(weights.values()) == 0:
        if total:
            with pytest.raises(ValueError, match="zero weights"):
                split_pro_rata(total, weights)
        return
    parts = split_pro_rata(total, weights)
    assert sum(parts.values()) == total
    weight_sum = sum(weights.values())
    for k, w in weights.items():
        assert abs(parts[k] - total * w / weight_sum) < len(weights) + 1
        assert parts[k] >= 0


def test_split_pro_rata_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="negative"):
        split_pro_rata(-1, {"a": 1})
    with pytest.raises(ValueError, match="negative"):
        split_pro_rata(1, {"a": -1})
    assert split_pro_rata(0, {"a": 0}) == {"a": 0}


def test_identifier_formats() -> None:
    assert ids.complaint_channel("21234567890123") is ids.ComplaintChannel.NCRP
    assert ids.complaint_channel("31234567890123") is ids.ComplaintChannel.HELPLINE_1930
    with pytest.raises(ValueError, match="acknowledgement"):
        ids.complaint_channel("41234567890123")
    assert ids.is_rrn(ids.new_rrn())
    assert ids.is_neft_utr(ids.new_neft_utr("SBIN"))
    assert ids.is_rtgs_utr(ids.new_rtgs_utr("HDFC"))
    assert ids.is_ncrp_ack(ids.new_ncrp_ack(ids.ComplaintChannel.HELPLINE_1930))
    assert ids.is_ifsc("SBIN0001234")
    assert not ids.is_ifsc("SBIN1001234")
    assert ids.is_vpa("galaxy.mobiles@okaxis")
    assert not ids.is_vpa("no-at-sign")
    assert ids.is_mobile("9876543210")
    assert not ids.is_mobile("5876543210")
    with pytest.raises(ValueError, match="4 capital letters"):
        ids.new_neft_utr("sbi")


def test_gstin_check_character() -> None:
    first14 = "27AAPFU0939F1Z"
    valid = first14 + ids.gstin_check_char(first14)
    assert ids.is_gstin(valid)
    wrong = first14 + ("A" if valid[-1] != "A" else "B")
    assert not ids.is_gstin(wrong)
    assert not ids.is_gstin("not a gstin")
    with pytest.raises(ValueError, match="14 GSTIN"):
        ids.gstin_check_char("short")
