# ripple-sim

The payment network simulator. It plays every customer in the simulated network: it opens accounts and posts each
payment to the ledgers of the institutions involved, so each institution keeps only its own ledger. A payment
between two institutions is two postings with the same `Payment`: a debit at the payer's and a credit at the
payee's. Money that leaves the banking system (cash at an ATM, a card payment, a crypto withdrawal) is one debit
with an `ExitDetail` naming the ATM, merchant or wallet.

```
uv run ripple-sim --seed 7 --out data/sim
```

This writes `deliveries.jsonl` (one message per line for one member's node, in time order), `story.json` (the
demo story's accounts, payments and the traced amounts the PRD expects) and `scams.json` (the other scam shapes,
with each victim's complaint). A seed always gives the same files.

## Posting to the network

```
uv run ripple certs   # once
uv run ripple up      # in another terminal
uv run ripple-sim --seed 7 --out data/sim --post
```

`--post` sends every delivery to its member's node over mutual TLS, signed as the party "sim": each
`AccountOpening` to `/v1/accounts`, and each member's `LedgerPosting`s in order to `/v1/postings`, in batches of
`--batch-size` (200). A batch is all or nothing.

- Nodes trace only what has happened by their own clock, so without `--month` the simulator runs the last full
  month before the network's clock, and it refuses to post anything dated after it.
- Transaction IDs and UPI IDs carry the seed, so several seeds can go to one network. Posting the same seed twice
  fails, because each node refuses an account it already holds.
- `packages/ripple-sim/tests/test_post.py` posts a month through the in-process network and checks the hub's
  trail against `story.json`.

## What it simulates

- **The network:** Bank A to D, Wallet W and Exchange X, read from `network.toml` (`network.py` adds a city for
  ATM and shop locations). IFSCs and NEFT and RTGS UTRs start with the member's code, and UPI IDs end with its
  handle.
- **A month of ordinary traffic** (`traffic.py`):
  - salaries by NEFT on each employer's payday, between the 1st and the 7th;
  - rent once between the 1st and the 5th;
  - UPI purchases at shops and transfers between people;
  - shops paying suppliers weekly;
  - electricity bills;
  - ATM withdrawals and debit card payments;
  - wallet top-ups and spending;
  - exchange deposits followed by crypto withdrawals.

  A payment the payer can't afford at that moment is declined, so no balance goes below zero.
- **The PRD's demo story** (`scenario.py`), step for step as `ripple demo` plays it
  (`packages/ripple-cli/src/ripple_cli/demo.py`): every payment by minute 8 and the 1930 call at minute 12.
  - Rs 8,00,000 RTGS from the victim at Bank A to M1 at Bank B.
  - M1 keeps Rs 1,00,000 and sends Rs 3,00,000 to M2 at Bank C and Rs 2,50,000 to M3 at Bank D by IMPS, and
    Rs 1,50,000 to Wallet W.
  - M2 takes Rs 2,00,000 at two ATMs and sends Rs 1,00,000 to Exchange X.
  - M3, with Rs 3,00,000 of its own, pays Ravi Traders Rs 2,00,000 by NEFT, Galaxy Mobiles Rs 1,20,000 by IMPS
    and a Rs 15,000 salary by IMPS.

  The tests trace the mules' ledgers with `ripple_core.tracing` and check the PRD's figures: Ravi Traders
  Rs 2,00,000, Galaxy Mobiles Rs 50,000 and the salary Rs 0.
- **Three more scam shapes** (`scams.py`), so detection is not tuned to one story. Their amounts and times are
  fixed; the patterns follow public reporting, and the amounts are ours.
  - *Investment scam:* 14 UPI transfers over four days, each under UPI's Rs 1 lakh cap, into two mules who keep
    2% and forward the rest within the hour to a collector, who turns each day's money into crypto that night. The
    victim reports before the fourth night's withdrawal, so that day's money is still at the exchange.
  - *Patient mule:* Rs 3,40,000 by IMPS late in the evening; the mule waits nine hours, then forwards Rs 1,90,000
    and takes cash in Rs 10,000 withdrawals; a second mule waits six more hours. Rs 1,20,000 is still with the
    first mule when the victim reports the next afternoon.
  - *Task scam:* four victims pay escalating "task deposits" by UPI into one shop's current account, which also
    takes genuine payments. Each victim files a separate complaint, so the hold is shared among them pro rata
    (SOP Annexure V, illustration 2).

## Where the numbers come from

The month follows published figures where one exists. The constants at the top of `traffic.py` name them, and
`test_traffic.py::test_the_month_matches_the_published_figures` checks that a simulated month stays close to them.

| Figure | Value used | Source |
| --- | --- | --- |
| UPI volume | context only: 24.07 billion payments worth Rs 29.37 lakh crore in September 2026 (802 million a day) | NPCI monthly statistics, as reported by [Outlook Money](https://www.outlookmoney.com/banking/upi-processes-2407-billion-transactions-worth-rs-2937-lakh-crore-in-september) |
| UPI split | 63% of UPI payments go to merchants (P2M), 37% between people (P2P) | FY 2025-26 figures from PIB, as reported by [Business Today, 24 Aug 2026](https://www.businesstoday.in/india/story/10-years-of-upi-transaction-value-surges-4000-fold-to-reach-rs314-lakh-crore-550975-2026-08-24) |
| P2M amounts | 86% below Rs 500; mean about Rs 635 | Same source for the 86%; [Worldline India Digital Payment Report 1H 2025](https://worldline.com/content/dam/worldline/local/en-in/documents/main-page11111/Worldline-India-Digital-Payment-Report-1H-2025-1.pdf) gives a P2M average of Rs 589 |
| P2P amounts | 59% below Rs 500; mean about Rs 2,500 | Same source for the 59%; the mean is our division of NPCI's February 2026 P2P value by its volume, as published by [Meetanshi](https://meetanshi.com/blog/upi-statistics/) (a secondary source) |
| UPI average overall | context only: Rs 1,313 in calendar 2025 | [RBI Payment System Report, December 2025](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=23813), para 2.20 |
| Debit card payments | about 0.6% of UPI volume; mean about Rs 3,430 | Same RBI report: 133.6 crore debit card payments worth Rs 4.5 lakh crore in 2025 (about Rs 3,370 each), against roughly 22,000 crore UPI payments |
| NEFT and IMPS | context only: NEFT about Rs 48,200 and IMPS about Rs 14,500 per payment in 2025 | Same RBI report (NEFT 1,000 crore payments worth Rs 482 lakh crore; IMPS 518 crore worth Rs 75 lakh crore) |
| ATM cash | Rs 500 to Rs 11,000 in Rs 500 steps, mean Rs 5,750 | CMS Info Systems: average withdrawal Rs 5,835 in 2025, as reported by [The Pioneer](https://dailypioneer.com/news/cash-withdrawals-from-atms-decline-in-2025-says-report) |
| Salary dates | each employer pays on one day between the 1st and the 7th | [Code on Wages, 2019, s.17(1)](https://www.advocatekhoj.com/library/bareacts/codeonwages/17.php): monthly wages before the end of the 7th day of the next month |
| Rail limits | UPI person-to-person up to Rs 1 lakh; IMPS up to Rs 5 lakh; RTGS from Rs 2 lakh | NPCI and RBI product rules (general limits, not re-fetched for this README) |

**No public figure exists**, so these are our own assumptions, stated here rather than dressed up as data:

- how many UPI shop payments one person makes a day (about 1.05) and how often they visit an ATM (about once a
  month). NPCI publishes totals, not payments per user;
- rent amounts (Rs 6,000 to Rs 32,000) and the rent day (the 1st to the 5th);
- electricity bill amounts (Rs 400 to Rs 4,500) and the week they are paid;
- shops' weekly supplier payments (Rs 20,000 to Rs 2,80,000), and who keeps a wallet or a crypto account;
- declared incomes by occupation, and opening balances;
- the scam shapes' exact amounts and times. Their patterns (many sub-Rs 1 lakh UPI transfers, layered mule
  accounts feeding a crypto exchange, mules recruited through fake job offers) follow public reporting such as
  [Sumsub on a 2026 trading-scam probe](https://sumsub.com/media/news/india-trading-scam-probe-identifies-mule-accounts/).

Identifiers come from the simulator's own seeded generator (`identifiers.py`). Each is checked with the
`ripple_core.ids` validators. `ripple_core.ids` generators use `secrets` and can't be reproduced. The messages are
`ripple_core.messages.AccountOpening` and `LedgerPosting`; the declared KYC profile travels as one line of text.
