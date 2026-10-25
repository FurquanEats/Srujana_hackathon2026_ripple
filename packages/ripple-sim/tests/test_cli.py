import json
from pathlib import Path

import pytest

from ripple_core.money import rupees
from ripple_sim.cli import main


def test_cli_writes_deliveries_and_the_story(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["--seed", "2", "--people-per-bank", "5", "--out", str(tmp_path)])

    lines = (tmp_path / "deliveries.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["kind"] == "account_opening"
    assert {json.loads(line)["kind"] for line in lines} == {"account_opening", "ledger_posting"}

    story = json.loads((tmp_path / "story.json").read_text(encoding="utf-8"))
    assert story["expected_traced"] == {
        "m3_to_ravi_traders": rupees("2,00,000"),
        "m3_to_galaxy_mobiles": rupees("50,000"),
        "m3_salary": 0,
    }
    assert story["steps"][0]["name"] == "victim_to_m1"
    assert story["steps"][0]["amount"] == rupees("8,00,000")
    assert story["accounts"]["m1"]["member"] == "bank-b"
    assert "₹8,00,000 reported" in capsys.readouterr().out
