import pytest

from ripple.packs import available_packs, load_pack


def test_india_pack_loads():
    assert "india" in available_packs()
    pack = load_pack("india")
    assert pack["currency"] == "INR"
    assert pack["report"] == {"type": "STR", "authority": "FIU-IND", "deadline_working_days": 7}


def test_fusion_weights_sum_to_one():
    weights = load_pack("india")["fusion"]["initial_weights"]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_tiers_are_ordered():
    t = load_pack("india")["tiers"]
    assert t["alert"] <= t["review"] <= t["critical"]


def test_unknown_pack():
    with pytest.raises(KeyError):
        load_pack("mars")
