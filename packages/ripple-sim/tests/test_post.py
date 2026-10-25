"""Posting a simulated month to the members' nodes, then tracing the demo story's complaint across them."""

import json
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from netharness import Net
from ripple_core.clock import IST, FixedClock
from ripple_core.messages import AccountOpening, AccountRef, Complaint, LedgerPosting, Payment
from ripple_core.money import rupees
from ripple_core.signing import Opened
from ripple_hubs.cfcfrms import Trail
from ripple_sim import cli, post
from ripple_sim.simulation import DEFAULT_MONTH, simulate
from ripple_sim.traffic import TrafficConfig

MONTH_END = datetime(2026, 11, 30, 23, 0, tzinfo=IST)


def file_complaint(net: Net, story: dict[str, Any]) -> Trail:
    """File the victim's 1930 complaint from story.json and read back the trail the hub built."""
    victim, m1 = story["accounts"]["victim"], story["accounts"]["m1"]
    step = story["steps"][0]
    complaint = Complaint(
        ack_number=story["ack_number"],
        victim_name=victim["holder"],
        payment=Payment(rail=step["rail"], reference=step["reference"], amount=step["amount"], at=step["at"]),
        beneficiary=AccountRef(ifsc=m1["ifsc"], account_number=m1["account_number"]),
        filed_at=story["reported_at"],
    )
    net.call("web", "cfcfrms", "/v1/complaints", complaint)
    return Trail.model_validate(
        net.call("web", "cfcfrms", "/v1/trails", {"ack_number": story["ack_number"]}).payload
    )


def test_a_posted_month_traces_the_story_as_story_json_expects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    net = Net(FixedClock(MONTH_END))
    monkeypatch.setattr(post, "connect", lambda root: post.Live(partial(net.call, "sim"), MONTH_END))

    code = cli.main(
        ["--seed", "4", "--people-per-bank", "4", "--out", str(tmp_path), "--post", "--batch-size", "50"]
    )

    assert code == 0
    assert "signed as sim" in capsys.readouterr().out
    story = json.loads((tmp_path / "story.json").read_text(encoding="utf-8"))
    assert story["reported_at"].startswith("2026-10-")  # the last full month before the network's clock
    trail = file_complaint(net, story)
    assert trail.complete
    assert trail.reported == rupees("8,00,000")
    assert trail.held == rupees("6,00,000")
    assert trail.cashed_out == rupees("2,00,000")
    assert trail.off_network == trail.not_found == trail.waiting == 0

    held = {a.account.account_number: a.held for a in trail.accounts}
    by_step = {s["name"]: s for s in story["steps"]}
    for name, expected in story["expected_traced"].items():
        payee = story["accounts"][by_step[name]["payee"]]["account_number"]
        assert held.get(payee, 0) == expected, name
    atms = sorted(e.identifier for a in trail.accounts for e in a.exits)
    assert atms == sorted(s["exit_identifier"] for s in story["steps"] if s["exit_identifier"])


def test_every_delivery_reaches_its_node() -> None:
    sim = simulate(seed=9, config=TrafficConfig(month=DEFAULT_MONTH, people_per_bank=3, shops_per_bank=2))
    net = Net(FixedClock(MONTH_END))

    result = post.post(sim.deliveries, partial(net.call, "sim"), batch_size=100)

    openings = sum(isinstance(d.message, AccountOpening) for d in sim.deliveries)
    assert result.accounts == openings
    assert result.postings == len(sim.deliveries) - openings
    with pytest.raises(Exception, match="409"):  # a node refuses an account it already holds
        post.post(sim.deliveries[:1], partial(net.call, "sim"))


def test_several_seeds_can_be_posted_to_one_network() -> None:
    net = Net(FixedClock(MONTH_END))
    config = TrafficConfig(month=DEFAULT_MONTH, people_per_bank=3, shops_per_bank=1)
    for seed in (1, 11):  # "11" followed by 3 digits never equals "1" followed by 3 digits
        post.post(simulate(seed=seed, config=config).deliveries, partial(net.call, "sim"))
    with pytest.raises(ValueError, match="negative"):
        simulate(seed=-1, config=config)


def test_postings_are_batched_per_member_and_sent_before_that_member_opens_another_account() -> None:
    sim = simulate(seed=2, config=TrafficConfig(month=DEFAULT_MONTH, people_per_bank=2, shops_per_bank=1))
    calls: list[tuple[str, str, int]] = []

    def send(member: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
        size = len(payload["postings"]) if isinstance(payload, dict) else 1
        calls.append((member, path, size))
        return Opened(member, "sim", MONTH_END, "-", {})

    bank_a = [d for d in sim.deliveries if d.member == "bank-a"]
    opening = next(d for d in bank_a if isinstance(d.message, AccountOpening))
    posting = next(d for d in bank_a if isinstance(d.message, LedgerPosting))
    result = post.post([posting, opening], send, batch_size=10)

    assert calls == [("bank-a", "/v1/postings", 1), ("bank-a", "/v1/accounts", 1)]
    assert (result.accounts, result.postings, result.batches) == (1, 1, 1)

    calls.clear()
    result = post.post(sim.deliveries, send, batch_size=7)
    assert all(size <= 7 for _, path, size in calls if path == "/v1/postings")
    assert sum(size for _, path, size in calls if path == "/v1/postings") == result.postings
    with pytest.raises(ValueError, match="at least 1"):
        post.post([], send, batch_size=0)


def test_post_explains_how_to_start_the_network_when_it_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def down(root: Path) -> post.Live:
        raise ConnectionError("connection refused")

    monkeypatch.setattr(post, "connect", down)
    assert cli.main(["--seed", "2", "--people-per-bank", "2", "--out", str(tmp_path), "--post"]) == 1
    assert "ripple up" in capsys.readouterr().err


def test_post_refuses_a_month_after_the_networks_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[str] = []

    def send(member: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
        sent.append(path)
        return Opened(member, "sim", MONTH_END, "-", {})

    monkeypatch.setattr(post, "connect", lambda root: post.Live(send, MONTH_END))
    args = [
        "--seed",
        "2",
        "--people-per-bank",
        "2",
        "--out",
        str(tmp_path),
        "--post",
        "--month",
        "2026-12-01",
    ]
    assert cli.main(args) == 1
    assert "earlier --month" in capsys.readouterr().err
    assert sent == []


def test_posting_a_seed_twice_says_why_it_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    net = Net(FixedClock(MONTH_END))

    def send(member: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
        try:
            return net.call("sim", member, path, payload)
        except Exception as exc:  # as `mtls_post` reports any failed call
            raise ConnectionError(str(exc)) from exc

    monkeypatch.setattr(post, "connect", lambda root: post.Live(send, MONTH_END))
    args = ["--seed", "2", "--people-per-bank", "2", "--out", str(tmp_path), "--post"]
    assert cli.main(args) == 0
    assert cli.main(args) == 1
    assert "post a seed only once" in capsys.readouterr().err


def test_the_default_month_for_posting_is_the_last_full_month() -> None:
    assert post.month_before(datetime(2026, 10, 25, 22, 0, tzinfo=IST)) == date(2026, 9, 1)
    assert post.month_before(datetime(2027, 1, 1, 0, 30, tzinfo=IST)) == date(2026, 12, 1)
