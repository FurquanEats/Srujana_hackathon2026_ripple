# Ripple

Ripple detects fraud and money-mule activity in Indian payments that only shows up across many transactions and accounts. It scores every UPI, IMPS, NEFT, RTGS and cash transaction as it streams in, groups linked alerts into cases ranked by expected loss, and explains each flag with the transactions behind it.

Built for Srujana Tech Fest 2026, Finance theme, problem statement F-01: Financial Fraud and Transaction Risk Detection.

Ripple gives risk indicators for a human analyst to review. It does not decide that anyone committed fraud, it does not file reports, and it uses only synthetic and public data.

## How it works

```
replay / India simulator -> event bus -> per-account feature store
        -> typology detectors | behavioural baseline | graph layer | calibrated ML model
        -> fusion -> alerts -> incremental case engine -> REST + WebSocket -> Next.js UI
```

- **Typology detectors** find pass-through, fan-in then out, fan-out bursts, scatter-gather, temporal cycles, cash structuring under the Rs 50,000 PAN limit, and device takeover. Each reason cites transaction IDs.
- **Behavioural baseline** compares a transaction with the account's own history (robust z-scores, Isolation Forest).
- **Graph layer** finds rings and collector accounts on a rolling 7-day payment and device graph.
- **ML model** is LightGBM on behavioural and graph features, trained on IBM's public AML dataset with a time split, calibrated and explained with SHAP.
- **Fusion** combines the four layers. A transaction backed only by the baseline layer cannot rise above Watch, so unusual but honest customers stay out of the top of the queue. Missing device or location data lowers confidence instead of raising risk.
- **Cases** merge alerts that share accounts within 24 hours and are tiered Critical, Review or Watch, ranked by probability times amount at risk.

## Run it

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn ripple.api.main:app --reload
pytest -q
```

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

Copy `.env.example` to `.env` to change the API URL or CORS origins.

## API

| Route | Returns |
| --- | --- |
| `GET /cases?budget=N` | Top N open cases by expected loss |
| `GET /cases/{id}` | Case detail: reasons, SHAP values, money-flow graph, timeline, account profiles |
| `POST /cases/{id}/feedback` | Records an analyst verdict and returns the updated fusion weights |
| `GET /eval` | Evaluation report: metrics, ablation, per-typology recall, alert-budget curve |
| `WS /ws/stream` | Scored transactions and case updates as they happen |

Shapes are defined in `backend/ripple/schema.py`. `fixtures/` holds sample responses that validate against them.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/ripple/api` | FastAPI routes and WebSocket |
| `backend/ripple/stream`, `features` | Event bus, replay and per-account feature store |
| `backend/ripple/detectors`, `fusion.py`, `cases.py`, `feedback.py` | Detection, scoring, case engine and feedback learning |
| `backend/ripple/models`, `eval` | ML models and evaluation |
| `backend/ripple/sim`, `data` | India transaction simulator and IBM AML loader |
| `backend/ripple/copilot`, `india` | Case narratives, STR drafts and Indian compliance rules |
| `backend/ripple/packs` | Region thresholds as YAML |
| `fixtures/` | Sample API responses |
| `frontend/` | Next.js app |

## Status

| Part | State |
| --- | --- |
| API contract, routes, WebSocket and tests | Working, serving sample data from `fixtures/` |
| India pack thresholds | Working |
| Case queue page | Working against the API |
| Detectors, feature store, graph layer, model, fusion, case engine | In progress |
| Simulator, IBM AML loader, evaluation | In progress |
| Workbench, budget optimiser, evaluation page, copilot | In progress |

The numbers in `fixtures/eval.json` are illustrative sample data, not measured results.

## Data

- [IBM Transactions for Anti Money Laundering](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml) (public, synthetic) for training and evaluation. Not committed; place it in `data/raw/`.
- Ripple's own India simulator for demo scenarios. Labels are hidden from the engine.

## AI usage

The team used AI coding assistants (Claude Code) to plan the architecture and to draft code, tests and documentation. Every change is reviewed and integrated by the team, and the team can explain each module.
