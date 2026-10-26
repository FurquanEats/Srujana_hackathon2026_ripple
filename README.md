# Ripple

**Follow stolen money across banks in seconds, and hold only what is traced.**

Ripple is software each bank runs beside its core banking and fraud systems. In India today, when a scam victim calls 1930, CFCFRMS (MHA/I4C) sends a notice to the bank that received the money, and that bank's nodal officer holds what is left or reports the next transfer by hand. Each hop waits for a person at a different bank, while mule money moves in minutes. From April 2021 to November 2025, CFCFRMS held Rs 7,647 crore of Rs 52,969 crore reported, and only Rs 167 crore reached victims (MHA SOP for NCRP-CFCFRMS, January 2026).

A Ripple node answers each CFCFRMS notice in one step. It traces the victim's money through the account with the rule the SOP's own examples use, places a lien on the traced amount only, and reports the next hops and any ATM or wallet identifiers. The same node runs RBI's draft temporary debit hold on suspected mule accounts with every deadline, checks a payee before money leaves, and helps the bank release honest account holders quickly by checking the documents they send against the held credits.

Built for Srujana Tech Fest 2026, Finance theme, problem statement F-01: Financial Fraud and Transaction Risk Detection. Ripple gives officers traced amounts, verdicts and drafts to review. It does not decide that anyone committed fraud, and it uses only synthetic data.

**Live demo:** https://srujana-hackathon2026-ripple.vercel.app. Choose **Workspace**, then any role. There is no password, because every record is synthetic.

## What is built

The requirement IDs are the PRD's.

| Area | Built | Planned |
| --- | --- | --- |
| Notice responder (CFCFRMS) | N1 match a notice to the credit by UTR or RRN, amount and time; N2 trace by the SOP's Annexure V rule; N3 lien on the traced amount only; N4 onward hops carry only the victim's money; N5 exits with ATM, merchant and wallet identifiers | N6 account-type rules for nodal, pool and escrow accounts; N7 the KYC upload; N8 the repeat-report advice; N9 the bank's auto-hold policy |
| Mule detection and RBI's temporary debit hold | M1 six red-flag rules, each flag citing its transactions; M2 hold the flagged amount, with a written reason for a whole-account hold; M3 the customer notice at once; M4 every clock (20 days to explain, the decision in 10 or 30 days, the report to police, release on day 31, the 60-day cap); M5 the STR draft and the breach when it is late; M6 the hash-chained audit log; M7 thresholds proposed by replaying the last 30 days, approved by an analyst | |
| Payment check | P1 a DPIP lookup by keyed hashes (about 30 ms on the simulated network); P2 allow, warn, cooling hold, or hold and call, combining DPIP, the bank's own flags and the coerced-transfer pattern; P3 a hold publishes a risk signal, and confirming a mule raises it | FRI, DoT's score for mobile numbers (the simulated accounts carry none) |
| Explanation review | G2 Gemini reads each document into fixed fields with the words behind each field; G3 fixed rules give each credit a verdict; G4 the officer confirms or overrules each verdict | G1 uploading the files themselves (the prototype records their names) |
| CFCFRMS hub | H1 complaints from 1930 and NCRP; H2 notices followed bank to bank; H3 the trail with totals that add up to the rupee; H4 held money split among victims by Annexure V | H5 the grievance deadlines (7 and 15 days, escalation, the 90-day rule) |
| Screens | The bank workspace (notices, liens, mule flags, holds, detection, payment checks, audit log), the trail with a replay slider, the account holder's hold page, the victim's status page, the grievance officer's evidence packs, police hold reports | The demo's side-by-side "today and Ripple" comparison |

## The web app

Sign in as any of seven roles. Each sees only what the gateway lets that role see.

| Role | Pages |
| --- | --- |
| Nodal officer (per bank) | Overview; CFCFRMS notices, each with the statement, the victim's money in green, the lien, onward hops and exits; liens; payment check; audit log |
| FRM analyst (per bank) | Overview with the nearest deadlines; mule flags, with hold placement and a preview of the customer notice; debit holds with the 20, 30 and 60-day timeline, decisions, mule confirmation and the STR draft; detection thresholds with the 30-day shadow run; payment check; audit log |
| Grievance officer (per bank) | Evidence packs: each document as Gemini read it, with the quoted words behind each field, the rules' checks and verdict for each held credit, and confirm or overrule |
| Police officer | Overview; every complaint's trail as a graph with a replay slider; hold reports, where the police tell a bank to continue or release a hold |
| Account holder | The bank's notice, the deadlines, and an explanation to send |
| Victim | What is held, at which bank, and how it can be returned |
| Demo operator | Plays the PRD's demo story on the network |

The hosted site runs on gateway responses saved from a real run of the network (`web/lib/gateway/fixtures/`), so it needs no backend. A visitor's own changes on it, such as placing a hold, are kept in their browser and follow the same rules as the bank node. With `RIPPLE_GATEWAY=live`, every page reads and writes the running network instead.

## Run it

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 24.

```bash
uv sync                                         # install the Python packages
uv run ripple certs                             # once: a local CA, TLS certificates and signing keys in .ripple/
uv run ripple up --fresh                        # start the hub, six institutions and the web gateway
uv run ripple-sim --seed 7 --out data/sim --post   # in a second terminal: a month of ordinary Indian traffic
uv run ripple demo                              # the PRD's digital-arrest story, traced across six institutions
```

The web app, on saved data or on the running network:

```bash
cd web
npm ci
RIPPLE_DEMO=1 npm run dev                       # saved data, at http://localhost:3000
RIPPLE_DEMO=1 RIPPLE_GATEWAY=live npm run dev   # the running network, through the gateway on 127.0.0.1:8090
```

`RIPPLE_DEMO=1` turns on the password-free sign-in. In live mode the web server signs a short-lived session token for every gateway call with the secret in `.ripple/gateway.secret`, or in `GATEWAY_SECRET` if set; the secret never reaches the browser. To refresh the saved data from a fresh network, run `uv run python scripts/capture_web_fixtures.py` after the simulated month, and `uv run python scripts/capture_review_fixtures.py` for the evidence packs.

Checks:

```bash
uv run ruff format --check packages && uv run ruff check packages && uv run mypy packages
uv run pytest --cov                             # 197 tests, 87% coverage (the floor is 85%)
cd web && npm run lint && npm run typecheck && npm test && npm run build && npm run e2e
```

## Results

**The demo story.** A retired teacher sends Rs 8,00,000 by RTGS to a mule at Meridian Private Bank. Within nine minutes it is split across three more institutions, partly withdrawn at two ATMs and partly paid to shops. Twelve minutes later she calls 1930. The trail completes in under a second across six institutions: Rs 6,00,000 held across five accounts, Rs 2,00,000 withdrawn at two named ATMs, and nothing liened that is not the victim's money. The shop's assistant, paid after the victim's money ran out, gets no notice.

**The next victim.** A customer of Pragati Small Finance Bank who tries to pay Rs 4,00,000 to the same mule the next day gets "hold and call": DPIP finds the mule on the suspect registry built from CFCFRMS trails. A payment to the cement supplier that the mule paid for goods is allowed.

**The document review.** On the synthetic document set (`eval/documents/`, 17 cases and 18 documents covering genuine invoices, a TDS deduction, an e-invoice, Hindi scans, a reused invoice, an invalid GSTIN, a late invoice and planted instructions to the reviewer), Gemini 3.5 Flash read every document:

| Measure | Result |
| --- | --- |
| Credits with the right verdict | 17 of 19 |
| Mismatched, reused or planted-instruction documents marked explained | 0 |
| Fields read exactly as printed | total 88%, date 88%, issuer GSTIN 94%, payment reference 82% |

The two misses are safe ones: a salary slip and a rent agreement were marked "not explained" instead of "explained". A salary slip gives a pay period instead of a date, and the rent agreement gives a monthly rent but no total, so the rules would not clear the credit without them. As a cross-check, Gemini 3 Flash (preview) read the same set with the same result: 17 of 19 credits right, the same two safe misses, and none wrongly cleared. The first run of this evaluation found three bad documents marked explained, because Gemini writes dates day first and document types in words, and the rules then skipped the date and GSTIN checks. The rules now read Indian dates, normalise document types, and fail a check they cannot read; a test feeds every case in the model's own spelling. Full results are in `eval/documents/review_results.json`.

## How it works

| Package | What it does |
| --- | --- |
| `packages/ripple-core` | Money in paise, Indian payment identifiers (NCRP acknowledgements, RRN, NEFT and RTGS UTRs, IFSC, UPI IDs, GSTIN), the messages, Ed25519-signed envelopes, the simulated clock, tracing, and DPIP's keyed identifier hashes |
| `packages/ripple-node` | The bank node: the bank's own ledger view, liens, automatic answers to CFCFRMS notices, mule detection, RBI's temporary debit hold, the payment check and the audit log |
| `packages/ripple-hubs` | The simulated CFCFRMS hub, which routes notices bank to bank until the trail is complete, and the simulated DPIP |
| `packages/ripple-gateway` | The web app's only door into the network: it checks each request's role and bank, then calls the nodes and hubs over mutual TLS |
| `packages/ripple-review` | The explanation review: Gemini fills a fixed schema with quotes, and fixed rules decide each verdict |
| `packages/ripple-sim` | A month of ordinary Indian payments with sourced figures, the demo story and three more scam shapes |
| `packages/ripple-service` | Shared plumbing: configuration, signed requests over mutual TLS, a replay store and an append-only audit log |
| `packages/ripple-cli` | The `ripple` command: `certs`, `up` and `demo` |
| `web/` | The Next.js web app: the home page and the workspace |
| `network.toml` | The simulated network: the hub, four banks (Navodaya National, Meridian Private, Pragati Small Finance, Sangam Urban Co-operative), PaySetu Wallet and CoinKosh Exchange, all fictional |

**Tracing.** A debit takes the victims' money before the account holder's own money, shared pro rata among victims. This rule reproduces both worked examples in Annexure V of the MHA SOP exactly, and both are tests. Once a lien is placed, that money is set aside, and later payments cannot be counted as taking it.

**Detection.** Six rules flag credits of Rs 1,000 or more (RBI draft, Annex III 3(8)): pass-through, many new senders, out of the declared profile, dormant then busy, quick cash-out, and linked to a reported account. A bank sets its own thresholds: Ripple replays the last 30 days at a range of settings and proposes the most sensitive ones within the number of flags the team can review in a day, measured against known outcomes. No model is trained.

**Security.** Every institution runs as its own process with its own database and keys, so no bank can read another's data. Services accept only mutually authenticated TLS, every message is signed and protected against replay, and each key is bound to one institution. DPIP stores and compares only HMAC hashes of account numbers and UPI IDs. The gateway accepts only short-lived HS256 session tokens and lets each role reach only its own bank; the account holder's and the victim's views leave out other people's details. Every service keeps an append-only, hash-chained audit log. The web app sets a content security policy and keeps the gateway secret on the server. CI runs ruff, mypy in strict mode, pytest with an 85% coverage floor, pip-audit, Gitleaks, Semgrep, and the web job (npm audit, ESLint, Prettier, TypeScript, Vitest, Playwright with axe).

**What is simulated.** CFCFRMS, RBIH's DPIP, DoT's Financial Fraud Risk Indicator and NPCI are not open to the public, so the hubs and institutions are simulated. The messages carry the fields the SOP requires banks to report, in a format we designed, because the NCRP API specification is not public. DPIP's pre-payment payee score is a planned phase of a seven-bank pilot; Ripple simulates it.

## The earlier version

The first version of Ripple, built in the first day of the hackathon, is in the git history (commit `2b3fcb3`, in the folder `backup/` that was removed later). It traced money inside a single bank only. We rebuilt Ripple because banks cannot see a payment once it leaves them, and the real-world fix is to make every bank's answer to CFCFRMS instant and exact.

## AI usage

AI tools were used, as the hackathon rules allow. Most of the code was written with an AI coding assistant (Claude Code, by Anthropic), working under the team's direction: the team set the design and the requirements, decided every trade-off, reviewed the changes and tested the result. AI also helped research and summarise Indian regulations, draft tests and documentation, and review the code for bugs and security issues. Inside the product, Google Gemini reads documents into fixed fields for the explanation review; fixed rules make every decision, and an officer confirms it.

## Acknowledgements

- Regulations and procedures: the MHA/I4C Standard Operating Procedure for NCRP-CFCFRMS (January 2026), RBI's draft directions on suspected money mule accounts (Annex III, 11 September 2026), and the Bharatiya Nagarik Suraksha Sanhita, 2023.
- APIs: Google Gemini, through the `google-genai` SDK.
- Data: every record is synthetic. The first version was also evaluated on IBM's public synthetic AML transactions dataset.
- Open-source libraries: FastAPI, Pydantic, SQLAlchemy, httpx, cryptography, pypdfium2, Pillow, Next.js, React, Tailwind CSS, jose, pytest, Hypothesis, Vitest, Playwright and axe-core, under their own licences. Fonts: Geist, Pixel Operator and DejaVu Sans.

## Team

Mohammed Furquan, Haameem and Tina, for Srujana Tech Fest 2026. The project report describes each person's part.
