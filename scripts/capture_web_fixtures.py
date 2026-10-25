"""Save the web gateway's answers from a running network as the web app's fixtures.

Run on a fresh network after posting a simulated month:

    uv run ripple up --fresh
    uv run ripple-sim --seed 7 --out data/sim --post
    uv run python scripts/capture_web_fixtures.py

It files the simulated story's and scams' complaints as a police officer, plays the demo story, then saves every
GET the workspace makes, for every role and institution, under web/lib/gateway/fixtures/. Tokens are signed with
the gateway's own secret, exactly as the web app's server signs them.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from ripple_gateway.auth import Role, issue, load_secret

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8090")
OUT = ROOT / "web" / "lib" / "gateway" / "fixtures"
INSTITUTIONS = ["bank-a", "bank-b", "bank-c", "bank-d", "wallet-w", "exchange-x"]
SECRET = load_secret(ROOT / ".ripple" / "gateway.secret", os.environ.get("GATEWAY_SECRET"))


def headers(role: Role, member: str | None) -> dict[str, str]:
    token = issue(SECRET, sub=f"demo-{role.value}", role=role, member=member, now=int(time.time()))
    return {"X-Ripple-Session": token}


def get(role: Role, member: str | None, path: str) -> Any:
    response = httpx.get(GATEWAY + path, headers=headers(role, member), timeout=60)
    response.raise_for_status()
    return response.json()


def post(role: Role, member: str | None, path: str, body: dict[str, Any]) -> httpx.Response:
    return httpx.post(GATEWAY + path, headers=headers(role, member), json=body, timeout=60)


def file_complaints() -> None:
    """One complaint per reported payment, as a police officer files them on CFCFRMS."""
    sim = ROOT / "data" / "sim"
    story = json.loads((sim / "story.json").read_text(encoding="utf-8"))
    scams = json.loads((sim / "scams.json").read_text(encoding="utf-8"))
    shapes = [
        {**story, "reports": [{"ack_number": story["ack_number"], "victim": "victim",
                               "steps": [story["steps"][0]["name"]], "reported_at": story["reported_at"]}]},
        *scams,
    ]  # fmt: skip
    for shape in shapes:
        steps = {step["name"]: step for step in shape["steps"]}
        for report in shape["reports"]:
            for name in report["steps"]:
                step = steps[name]
                payee = shape["accounts"][step["payee"]]
                body = {
                    "ack_number": report["ack_number"],
                    "victim_name": shape["accounts"][report["victim"]]["holder"],
                    "payment": {k: step[k] for k in ("rail", "reference", "amount", "at")},
                    "beneficiary": {
                        "ifsc": payee["ifsc"],
                        "account_number": payee["account_number"],
                        "vpa": None,
                    },
                    "filed_at": report["reported_at"],
                }
                response = post(Role.POLICE_OFFICER, None, "/v1/complaints", body)
                print(f"complaint {report['ack_number']} {name}: {response.status_code}")


HOLD_PLAN: list[tuple[str, str, list[tuple[str, dict[str, str]]]]] = [
    # (bank, holder, steps): each scripted hold shows one stage of RBI's Annex III procedure
    ("bank-a", "Ravi Traders", [("explanation", {"summary": "Payment for 400 bags of cement delivered to the "
                                                 "buyer's shop; tax invoice and delivery challan attached."})]),
    ("bank-b", "Galaxy Mobiles", [
        ("explanation", {"summary": "GST tax invoice for 12 phones sold to a corporate buyer, with the "
                                    "buyer's purchase order."}),
        ("decision", {"decision": "release", "reason": "The invoice and purchase order match the credit, and "
                                                      "selling phones fits the declared business."}),
    ]),
    ("bank-b", "Arjun Mondal", [("confirm-mule", {"grounds": "The account is on a CFCFRMS notice for the same "
                                                             "money, reported on the 1930 helpline."})]),
    ("bank-c", "Bikash Shaw", []),
    ("bank-d", "M3 General Store (mule)", [
        ("explanation", {"summary": "The customer sent no documents and said the money was a loan from a friend."}),
        ("decision", {"decision": "report", "reason": "No document supports the credit, which is five times the "
                                                     "declared turnover and left within two minutes."}),
    ]),
]  # fmt: skip


def run_holds() -> None:
    for bank, holder, steps in HOLD_PLAN:
        case = next(
            (c for c in get(Role.FRM_ANALYST, bank, "/v1/mule-cases") if c["holder_name"] == holder), None
        )
        if case is None:
            print(f"no open case for {holder} at {bank}")
            continue
        body = {"account_number": case["account_number"], "flag_keys": [f["key"] for f in case["flags"]],
                "contact": "Fraud Risk desk, 1800 000 0000, or frm@bank.example"}  # fmt: skip
        placed = post(Role.FRM_ANALYST, bank, "/v1/holds", body)
        print(f"hold {holder}: {placed.status_code}")
        if not placed.is_success:
            continue
        for path, step in steps:
            done = post(Role.FRM_ANALYST, bank, f"/v1/holds/{placed.json()['hold_id']}/{path}", step)
            print(f"  {path}: {done.status_code}")


def payment_checks(police: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Three payments checked before they leave, on the demo story's accounts (PRD demo step 7)."""
    trail = next(
        v
        for k, v in police.items()
        if k.endswith("/trail") and v["accounts"][0]["holder_name"] == "M1 (mule)"
    )
    m1 = trail["accounts"][0]["account"]
    ravi = next(
        a["account"] for a in trail["accounts"] if (a["holder_name"] or "").startswith("Ravi Traders")
    )
    flagged = {
        c["account_number"] for c in get(Role.FRM_ANALYST, "bank-c", "/v1/mule-cases?include_closed=true")
    }
    openings = (
        json.loads(line) for line in (ROOT / "data" / "sim" / "deliveries.jsonl").open(encoding="utf-8")
    )
    sender = next(
        d["message"]
        for d in openings
        if d["member"] == "bank-c"
        and d["kind"] == "account_opening"
        and d["message"]["declared_profile"].startswith("individual")
        and d["message"]["account_number"] not in flagged
    )  # an ordinary salaried customer of Bank C
    who = sender["account_number"]
    examples = [
        (
            "bank-c",
            "A customer of Bank C pays Rs 4,00,000 to M1, the mule from yesterday's scam",
            who,
            m1,
            40_000_000,
        ),
        ("bank-c", "The same customer pays Rs 2,000 to Ravi Traders, a cement supplier", who, ravi, 200_000),
    ]
    out: dict[str, list[dict[str, Any]]] = {}
    for bank, label, account, payee, amount in examples:
        body = {"sender_account": account, "payee": payee, "amount": amount}
        answer = post(Role.FRM_ANALYST, bank, "/v1/payment-check", body)
        print(f"check {label}: {answer.status_code}")
        if answer.is_success:
            out.setdefault(bank, []).append({"label": label, "request": body, "result": answer.json()})
    return out


def capture() -> dict[str, dict[str, Any]]:
    saved: dict[str, dict[str, Any]] = {}
    police: dict[str, Any] = {"/v1/cases": get(Role.POLICE_OFFICER, None, "/v1/cases")}
    for case in police["/v1/cases"]:
        path = f"/v1/cases/{case['ack_number']}/trail"
        police[path] = get(Role.POLICE_OFFICER, None, path)
    police["/v1/network"] = get(Role.POLICE_OFFICER, None, "/v1/network")
    police["/v1/hold-reports"] = get(Role.POLICE_OFFICER, None, "/v1/hold-reports")
    saved["police"] = police
    victims: dict[str, Any] = {}
    for case in police["/v1/cases"]:
        token = issue(SECRET, sub=case["ack_number"], role=Role.VICTIM, member=None, now=int(time.time()))
        answer = httpx.get(GATEWAY + "/v1/my-complaint", headers={"X-Ripple-Session": token}, timeout=60)
        victims[case["ack_number"]] = {
            "victim_name": case["victim_name"],
            "filed_at": case["filed_at"],
            **answer.json(),
        }
    saved["victims"] = victims
    checks = payment_checks(police)
    holders: dict[str, Any] = {}
    for member in INSTITUTIONS:
        nodal: dict[str, Any] = {"/v1/notices": get(Role.NODAL_OFFICER, member, "/v1/notices")}
        for notice in nodal["/v1/notices"]:
            path = f"/v1/notices/{notice['notice_id']}"
            nodal[path] = get(Role.NODAL_OFFICER, member, path)
        nodal["/v1/liens"] = get(Role.NODAL_OFFICER, member, "/v1/liens")
        frm: dict[str, Any] = {
            "/v1/mule-cases": get(Role.FRM_ANALYST, member, "/v1/mule-cases?include_closed=true"),
            "/v1/holds": get(Role.FRM_ANALYST, member, "/v1/holds"),
            "/v1/detection/thresholds": get(Role.FRM_ANALYST, member, "/v1/detection/thresholds"),
        }
        shadow = post(Role.FRM_ANALYST, member, "/v1/detection/shadow-run", {"budget_per_day": 5})
        frm["/v1/detection/shadow-run"] = shadow.json() if shadow.is_success else None
        frm["/v1/audit"] = get(Role.NODAL_OFFICER, member, "/v1/audit?limit=300")
        frm["payment-checks"] = checks.get(member, [])
        saved[f"bank.{member}"] = {**nodal, **frm}
        for hold in frm["/v1/holds"]:
            account = hold["account_number"]
            token = issue(SECRET, sub=account, role=Role.ACCOUNT_HOLDER, member=member, now=int(time.time()))
            answer = httpx.get(GATEWAY + "/v1/my-holds", headers={"X-Ripple-Session": token}, timeout=60)
            holders[f"{member}:{account}"] = {"holder_name": hold["holder_name"], "holds": answer.json()}
    saved["holders"] = holders
    saved["clock"] = {"/v1/clock": get(Role.DEMO, None, "/v1/clock")}
    return saved


def main() -> int:
    if "--no-complaints" not in sys.argv:
        file_complaints()
        demo = post(Role.DEMO, None, "/v1/simulation/demo-story", {})
        print(f"demo story: {demo.status_code} {demo.text}")
        time.sleep(5)  # the hub sends its notices and every bank answers
        run_holds()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, routes in capture().items():
        (OUT / f"{name}.json").write_text(json.dumps(routes, indent=1, ensure_ascii=False) + "\n", "utf-8")
        print(f"wrote {name}.json with {len(routes)} responses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
