"""The red team runs, and the blind spot it found first (a mule waiting 45 minutes) stays fixed."""

from ripple.redteam import ACTED_ON, Plan, RedTeam, transactions


def test_plans_turn_into_ordered_payments_that_end_in_a_cash_out():
    from datetime import datetime

    txns = transactions(Plan(victims=3, hops=2, split=2, cash_out="crypto"), datetime(2026, 10, 1), "T", ["A", "B", "C"])
    assert txns == sorted(txns, key=lambda t: t.ts)
    assert any(t.dst_account.startswith("P2P-") for t in txns)


def test_mule_waiting_45_minutes_is_now_caught():
    team = RedTeam(seed=3)
    trial = team.attack(Plan(victims=6, victim_amount=150_000, hops=1, split=1, delay_minutes=45, pass_share=0.85,
                             cash_out="crypto"))
    assert trial.max_probability >= ACTED_ON and not trial.evaded


def test_search_runs_and_reports_rounds():
    team = RedTeam(seed=3)
    log = team.run(rounds=2, population=6, keep=2)
    assert [r["round"] for r in log] == [1, 2] and all(r["plans"] == 6 for r in log)
