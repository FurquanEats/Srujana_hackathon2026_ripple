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


def capture() -> dict[str, dict[str, Any]]:
    saved: dict[str, dict[str, Any]] = {}
    police: dict[str, Any] = {"/v1/cases": get(Role.POLICE_OFFICER, None, "/v1/cases")}
    for case in police["/v1/cases"]:
        path = f"/v1/cases/{case['ack_number']}/trail"
        police[path] = get(Role.POLICE_OFFICER, None, path)
    police["/v1/network"] = get(Role.POLICE_OFFICER, None, "/v1/network")
    saved["police"] = police
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
        saved[f"bank.{member}"] = {**nodal, **frm}
    saved["clock"] = {"/v1/clock": get(Role.DEMO, None, "/v1/clock")}
    return saved


def main() -> int:
    if "--no-complaints" not in sys.argv:
        file_complaints()
        demo = post(Role.DEMO, None, "/v1/simulation/demo-story", {})
        print(f"demo story: {demo.status_code} {demo.text}")
        time.sleep(3)  # the hub sends its notices and every bank answers
    OUT.mkdir(parents=True, exist_ok=True)
    for name, routes in capture().items():
        (OUT / f"{name}.json").write_text(json.dumps(routes, indent=1, ensure_ascii=False) + "\n", "utf-8")
        print(f"wrote {name}.json with {len(routes)} responses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
