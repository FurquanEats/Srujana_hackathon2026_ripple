import pytest

from ripple.packs import available_packs, load_pack


def test_india_pack_loads():
    assert "india" in available_packs()
    pack = load_pack("india")
    assert pack["currency"] == "INR"
    assert pack["report"] == {"type": "STR", "authority": "FIU-IND", "deadline_working_days": 7}


def test_fusion_weights_cover_every_layer():
    weights = load_pack("india")["fusion"]["weights"]
    assert set(weights) == {"bias", "detector", "baseline", "graph", "model"}
    assert all(weights[k] > 0 for k in ("detector", "baseline", "graph", "model"))


def test_tiers_are_ordered():
    t = load_pack("india")["tiers"]
    assert t["alert"] <= t["review"] <= t["critical"]


def test_unknown_pack():
    with pytest.raises(KeyError):
        load_pack("mars")
