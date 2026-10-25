# Ripple

**Stop the scam, then follow the money.**

Ripple protects people from payment scams in India at the two moments that matter. Before the money leaves, it spots a customer being coached into draining their savings (a "digital arrest" or fake-investment scam) and recommends a cooling-off hold. After the money leaves, it follows the stolen funds hop by hop through mule accounts while they are still moving, shows where the money sits right now, and gives the bank's nodal officer the smallest set of liens on traced amounts that recovers the most, with a drafted hold request for each. And when a scam gets past every detector, Ripple learns its shape from that one confirmed trail and catches the next run of it, after checking against the bank's own traffic that ordinary customers almost never match.

Built for Srujana Tech Fest 2026, Finance theme, problem statement F-01: Financial Fraud and Transaction Risk Detection.

Ripple gives risk indicators and drafts for a human officer to review. It does not decide that anyone committed fraud, does not place liens on accounts or file reports itself, and uses only synthetic and public data.

## Why this matters

When a scam victim reports to the 1930 helpline or the cybercrime portal, the money has usually passed through two or three mule accounts within minutes, and some of it is already withdrawn or turned into crypto. Banks act on these reports by placing holds on receiving accounts, but tracing the money by hand across hops takes longer than the money takes to leave. Fraud scoring tools tell a bank which transaction looks risky; they do not tell an officer where the money is now and what to hold first.

## What Ripple does

| Moment | Capability | How |
| --- | --- | --- |
| Before | Pre-payment check | The bank asks Ripple at authorisation, before money moves (`POST /check`). Ripple scores the payment without recording it and answers in about a millisecond: allow, a 60-minute cooling-off hold the customer can release, or hold and call the customer. |
| Before | Coerced-transfer detection | An established customer sends most of a lump sum that just arrived from their own fixed deposit or long-known source to a payee they have never paid, at five or more times their usual payment and at least Rs 1 lakh. Repeats within 72 hours score higher. The recommended action is a cooling-off hold and a call to the customer or a trusted contact. |
| During | Streaming detection | Every payment is scored as it arrives by nine typology detectors (pass-through, fan-in then out, fan-out burst, scatter-gather, temporal cycle, cash structuring under the Rs 50,000 PAN-quote limit, device takeover, coerced transfer, rapid cash-out) and any patterns learned from confirmed trails, a behavioural baseline, a graph layer and an optional ML model, fused into one probability. |
| After | Golden-hour tracing | From a victim's report or an alerted case, Ripple follows the money forward through every hop it can see, using haircut taint tracking (the method used to trace mixed funds in crypto forensics). Money that reached an ATM withdrawal or a crypto off-ramp counts as escaped. |
| After | One-shot learning | When a victim reports a scam that no detector caught, the officer traces it and clicks "Learn this pattern". Ripple describes every account on the trail that received money and passed it on (how long the money sat, how much moved on, how many senders and payees, how old the account is, whether it has any spending of its own). It starts from the tightest description of those payments, frees the knobs a criminal changes cheaply between runs (amounts, waits, splits, hops), and stops before more than one ordinary payment every two days in the bank's last 30 days would match. The officer sees each rule with how rare it is, and the expected false alarms, before deploying it as a live detector. |
| After | Hold plan | Ripple proposes liens on the traced amount only, never a freeze of the whole account, in line with MHA's CFCFRMS procedure and recent High Court rulings. The accounts to hold are a minimum vertex cut between the traced money and cash-out points, weighted by how disruptive each hold would be, plus any account holding a large share of the traced money. When a mule's own money is mixed with stolen money, each hold is shown as a range under three accepted tracing rules (haircut, first in first out, and lowest intermediate balance), and the lien uses the lowest figure, which every rule supports. For this bank's own accounts the officer places the lien in one step; holds at other banks go out together as a structured CFCFRMS request. |

Every flag carries reason sentences that cite the transactions behind it and a counterfactual ("not flagged if the money had left more than 30 minutes after arriving"). Context signals alone (unusual for this account, near other alerts) can never push a case above Watch, so an unusual but honest customer, such as someone buying Diwali jewellery, is never escalated.

## Run the demo

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate              # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
RIPPLE_SOURCE=engine RIPPLE_DATA=sim:india RIPPLE_SPEED=1800 uvicorn ripple.api.main:app --port 8000
```

This simulates a legitimate month of Indian payments (salaries, rent, gig payouts, shops, UPI, IMPS, NEFT, RTGS and cash), scores the first 20 days at full speed as account history, then plays the rest live.

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev                         # http://localhost:3000
```

1. **Live:** live payments, engine throughput and latency, and the case queue. Click **Digital arrest** to inject a scam into the stream.
2. **Case workbench:** open the new Critical case. The hold plan shows money already escaped to an ATM and crypto, money still recoverable in mule accounts, and the traced amount to hold in each account. The replay slider shows the money moving hop by hop.
3. **Trace:** enter the victim's account, or a case number, to trace the money forward and place liens.
4. **Check:** check a payment before it goes. Try the coached transfer: a pensioner's broken FD followed by a ₹7.5 lakh transfer to a "safe account" comes back "hold and call".
5. **One-shot learning:** click **Patient mule ring**. Its mules wait just long enough that no built-in detector acts. About 20 seconds later, follow **Report it and trace the money**, then **Learn this pattern** and **Deploy as a live detector**. Click **Patient mule ring** again: the new ring becomes a Critical case citing the learned pattern, and the first ring's mules are flagged before they withdraw.
6. **Results:** results on IBM's public AML dataset, the red team and one-shot learning.

Run the tests with `cd backend && pytest -q`. Without `RIPPLE_SOURCE=engine`, the API serves the sample responses in `fixtures/`.

## Architecture

```
simulator or file replay -> ordered feed -> per-account feature store
    -> typology detectors | behavioural baseline | graph layer | ML model (optional)
    -> fusion -> alerts -> incremental case engine
    -> taint tracking + minimum-cut hold plan
    -> REST + WebSocket -> Next.js UI
```

| Choice | Why |
| --- | --- |
| Python engine, FastAPI, WebSockets | Same language as the ML stack, so live features are exactly the ones the model trains on; typed API contract in Pydantic |
| Rolling per-account state with binary-searched time windows | Constant cost per payment even for busy accounts; about 0.1 to 1 ms per payment on a laptop |
| NetworkX for communities, PageRank and the minimum cut | Recomputed only around alerted accounts, because whole-graph recomputes did not scale to IBM's 5 million transactions |
| Logistic fusion with a corroboration rule | Each layer's contribution is visible and can be refitted on labelled data or nudged by analyst feedback |
| Next.js, Cytoscape.js, Recharts | Live command centre, hop-by-hop money graph and evaluation charts |

## API

| Route | Returns |
| --- | --- |
| `GET /cases?budget=N` | Top N open cases, by tier then expected loss |
| `GET /cases/{id}` | Case detail: reasons, model contributions, money-flow graph, timeline, account profiles |
| `GET /cases/{id}/interdiction` | Hold plan: traced money, holdings, liens to request with their range across tracing rules, money escaped, recovery over time |
| `POST /trace` | Hold plan for a victim's report: `{account, from_ts?, amount?}`, or a case number |
| `POST /check` | Pre-payment check: `{src_account, dst_account, amount, rail}` → allow, cooling-off hold, or hold and call |
| `POST /liens`, `GET /liens?plan_id=`, `POST /liens/{id}/release` | Liens this bank places on its own accounts after an officer approves |
| `POST /inject/{kind}` | Adds a simulated scenario to the live stream (`digital_arrest`, `mule_ring`, `scam_fanout`, `sim_swap_takeover`, `cash_structuring`, `diwali_spike`, `patient_ring`) |
| `POST /motifs/learn` | Learns a pattern from one trail: `{case_id}` or a victim's report `{account, from_ts?, amount?}` |
| `GET /motifs`, `POST /motifs/{id}/deploy`, `POST /motifs/{id}/retire` | Learned patterns with their live matches; put one live or take it down |
| `POST /cases/{id}/feedback` | Records an analyst verdict and returns the updated fusion weights |
| `GET /eval`, `GET /redteam`, `GET /oneshot`, `GET /consortium` | Evaluation on IBM AML, red-team runs, one-shot learning results, consortium results |
| `POST /ingest`, `GET /stats`, `WS /ws/stream` | Push transactions, engine statistics, live stream of payments, cases and stats |

Shapes are defined in `backend/ripple/schema.py`.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/ripple/engine.py` | Runs every layer for each payment and updates cases |
| `backend/ripple/features` | Per-account rolling state and model features |
| `backend/ripple/detectors` | Typology detectors and the behavioural baseline |
| `backend/ripple/graph.py`, `fusion.py`, `cases.py`, `feedback.py` | Graph layer, fusion, case engine, feedback learning |
| `backend/ripple/motifs.py`, `redteam.py` | One-shot pattern learning; the adaptive red team |
| `backend/ripple/interdiction.py`, `trace.py`, `cash.py` | Taint tracking, hold plans, victim-report tracing, cash-in and cash-out rules |
| `backend/ripple/sim` | India payment simulator and scam scenarios |
| `backend/ripple/data`, `eval`, `models` | IBM AML loader, evaluation, LightGBM model |
| `backend/ripple/packs` | Thresholds per region as YAML (India; IBM AML evaluation in USD) |
| `backend/ripple/api` | FastAPI routes and WebSocket |
| `backend/scripts/benchmark.py` | Speed, memory and alert-quality benchmark on IBM AML |
| `frontend/` | Next.js app |
| `data/demo/` | Simulated India demo month |

## Data

- [IBM Transactions for Anti Money Laundering](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml), HI-Small (public, synthetic, labelled), for evaluation. Not committed; place the files in `data/raw/` and run `python -m ripple.data.ibm` from `backend/`.
- Ripple's India simulator for demo scenarios, with labels and victim flags kept out of the engine's view.

## Evaluation and validation

- Model and metrics on IBM AML use a time split: train on 3 to 7 September (after a 48-hour warm-up), test on 8 to 10 September. The sparse 11 to 18 September tail is replayed for state but not scored, because most of its rows are laundering and would inflate precision.
- The headline comparison is money still recoverable at the first alert, against a single-transaction rule. The fusion weights, the calibration of the fused probability and the alert threshold are all fitted on a held-out training day, never on the test days. On the test days Ripple reaches 62% precision at 37% recall (PR-AUC 0.39), against 1.9% precision for a single-transaction LightGBM given the same number of alerts, and 49 of its top 50 alerts are laundering. It alerts on 72% of laundering attempts, with a median of 94% of their money still recoverable at the first alert (7% of attempts and 0% for the baseline). Most of that ranking power comes from the LightGBM layer: in the same run the model alone has a slightly higher PR-AUC (0.42), while the pack's hand-set fusion weights reach only 0.05 on IBM.
- One-shot learning on IBM AML (`scripts/oneshot_ibm.py`) does not work yet, and we say so. Learning from the first attempt of each IBM laundering type, 2 of 8 types could be learned at all, and neither pattern caught a later attempt of its type. IBM's laundering hides inside ordinary, long-lived accounts and its types are defined by graph shape, so one attempt's account traits do not carry over; learning graph shapes from one example is the next step.
- One-shot learning (`scripts/oneshot_eval.py`, simulated India traffic): one red-team trail that never reached Review was the only example. The learned pattern catches all 38 of 120 random laundering plans the engine had missed, cuts the adaptive red team's evading plans from 37 to 0, and adds no false alarms on a different simulated bank over 30 days.
- On the simulated India month, false alarms were cut from 1,699 to 92 (84 of them Watch-level unusual amounts) while every scam scenario still reaches Review or Critical; `tests/test_false_alarms.py` keeps it that way.
- Each detector has a test for a hit, a near-miss just past its threshold, and missing data.

## Known limitations

- Tracing sees only payments inside the engine's 72-hour window and inside one bank's view; money that leaves the bank is counted as escaped.
- An account's own funds from before the engine's window are unknown, so traced holdings are an estimate; the three tracing rules bound it, but none of them is a legal determination.
- Cash-out accounts are recognised by name prefixes in the simulator; a bank would use its own list of ATMs and virtual-asset exchange accounts.
- Thresholds are set by hand for India and tuned on IBM AML, which is synthetic and US-dollar based; no real Indian bank data was used.
- A legitimate large purchase funded by a broken fixed deposit (a house down payment, say) looks like coercion, which is why the action is a hold and a call, not a block.
- Hold-request drafts and reason texts are not legal determinations.
- A learned pattern describes the relay accounts only, inside one bank's view, and its false-alarm estimate assumes the next 30 days look like the last 30. Accounts already active when monitoring began are treated as established, because their true age is unknown. One-shot learning works on simulated Indian mule rings but not yet on IBM AML (see Evaluation).

## AI usage

The team used AI coding assistants (Claude Code) to plan the architecture and to draft code, tests and documentation. Every change is reviewed and integrated by the team, and the team can explain each module.
