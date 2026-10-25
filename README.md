# Ripple

**Follow stolen money across banks in seconds, and hold only what is traced.**

Ripple is software each bank runs beside its core banking and fraud systems. In India today, when a scam victim calls 1930, CFCFRMS (MHA/I4C) sends a notice to the bank that received the money, and that bank's nodal officer holds what is left or reports the next transfer by hand. Each hop waits for a person at a different bank, while mule money moves in minutes. From April 2021 to November 2025, CFCFRMS held Rs 7,647 crore of Rs 52,969 crore reported, and only Rs 167 crore reached victims (MHA SOP for NCRP-CFCFRMS, January 2026).

A Ripple node answers each CFCFRMS notice in one step. It traces the victim's money through the account with the rule the SOP's own examples use, places a lien on the traced amount only, and reports the next hops and any ATM or wallet identifiers. When every bank on a trail runs Ripple, the whole trail completes in under a second, and the account holder's own money is never liened.

Built for Srujana Tech Fest 2026, Finance theme, problem statement F-01: Financial Fraud and Transaction Risk Detection. Ripple gives officers traced amounts and drafts to review. It does not decide that anyone committed fraud, and it uses only synthetic data.

## Run it

You need Python 3.12 and [uv](https://docs.astral.sh/uv/) (`pip install uv`).

```bash
uv sync                 # install everything
uv run ripple certs     # once: a local certificate authority, TLS certificates and signing keys in .ripple/
uv run ripple up        # start the CFCFRMS hub and six institutions, each as its own process
uv run ripple demo      # in a second terminal: run the demo scam and print the money trail
```

`ripple demo` runs the digital-arrest story from the PRD. A retired teacher sends Rs 8,00,000 to a mule at Bank B, which is split across three more institutions, partly withdrawn at two ATMs and partly spent at shops within nine minutes. Twelve minutes later the victim calls 1930. Ripple accounts for every rupee: Rs 6,00,000 held across five accounts, Rs 2,00,000 withdrawn at two named ATMs, and nothing liened that is not the victim's money.

Run the checks with:

```bash
uv run pytest
uv run ruff check packages && uv run mypy packages
```

## How it works

| Package | What it does |
| --- | --- |
| `packages/ripple-core` | Money in paise, Indian payment identifiers (NCRP acknowledgements, RRN, NEFT and RTGS UTRs, IFSC, UPI IDs, GSTIN), the notice and response messages, Ed25519-signed envelopes, the simulated clock, and tracing |
| `packages/ripple-node` | The bank node: the bank's own ledger view, liens, and automatic answers to CFCFRMS notices |
| `packages/ripple-hubs` | A simulated CFCFRMS hub that routes notices bank to bank until the trail is complete |
| `packages/ripple-service` | Shared plumbing: configuration, signed requests over mutual TLS, a replay store and an append-only audit log |
| `packages/ripple-cli` | The `ripple` command: `certs`, `up` and `demo` |
| `network.toml` | The simulated network: the hub, four banks, a wallet issuer and a crypto exchange (all fictional) |

**Tracing.** A debit takes the victims' money before the account holder's own money, shared pro rata among victims. This rule reproduces both worked examples in Annexure V of the MHA SOP exactly, and both are tests. Once a lien is placed, that money is set aside, and later payments cannot be counted as taking it.

**Security.** Every institution runs as its own process with its own database and keys, so no bank can read another's data. Services accept only mutually authenticated TLS, every message is signed and protected against replay, and each key is bound to one institution. Every service keeps an append-only, hash-chained audit log. CI runs ruff, mypy in strict mode, pytest with an 85% coverage floor, pip-audit, Gitleaks and Semgrep.

**What is simulated.** CFCFRMS, RBIH's DPIP, DoT's Financial Fraud Risk Indicator and NPCI are not open to the public, so the hubs and institutions are simulated. The messages carry the fields the SOP requires banks to report, in a format we designed, because the NCRP API specification is not public.

## In progress

- The web app for bank officers, police and account holders.
- The multi-bank simulator with a month of ordinary Indian traffic.
- RBI's draft money-mule hold procedure (20-, 30- and 60-day deadlines) with STR drafts.
- The DPIP and FRI payment check before money leaves.
- The Gemini explanation review, which checks an account holder's invoices against held credits so innocent holders are released quickly. The synthetic document set is in `eval/documents/`.

## The earlier version

The first version of Ripple, built in the first day of the hackathon, is in `backup/`. It traced money inside a single bank only. We rebuilt Ripple because banks cannot see a payment once it leaves them, and the real-world fix is to make every bank's answer to CFCFRMS instant and exact.

## AI usage

The team used AI coding assistants (Claude Code) to research Indian regulations, plan the architecture, and draft code, tests and documentation. The team reviews every change and can explain each module.
