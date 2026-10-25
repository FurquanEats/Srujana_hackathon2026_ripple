# ripple-sim

The payment network simulator. It plays every customer in the simulated network: it opens accounts and posts each
payment to the ledgers of the institutions involved, so each institution keeps only its own ledger. A payment
between two institutions is two postings with the same `Payment`: a debit at the payer's and a credit at the
payee's. Money that leaves the banking system (cash at an ATM, a card payment, a crypto withdrawal) is one debit
with an `ExitDetail` naming the ATM, merchant or wallet.

```
uv run ripple-sim --seed 7 --out data/sim
```

This writes `deliveries.jsonl` (one message per line for one member's node, in time order) and `story.json` (the
demo story's accounts, payments and the traced amounts the PRD expects). A seed always gives the same files.

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
  - salaries by NEFT on the 1st;
  - rent once between the 1st and the 5th;
  - UPI purchases at shops and transfers between people;
  - shops paying suppliers weekly;
  - electricity bills;
  - ATM withdrawals and card payments;
  - wallet top-ups and spending;
  - exchange deposits followed by crypto withdrawals.

  A payment the payer can't afford at that moment is declined, so no balance goes below zero.
- **The PRD's demo story** (`scenario.py`), with its exact amounts:
  - Rs 8,00,000 RTGS from the victim at Bank A to M1 at Bank B.
  - M1 keeps Rs 1,00,000 and sends Rs 3,00,000 to M2 at Bank C, Rs 2,50,000 to M3 at Bank D and Rs 1,50,000 to
    Wallet W.
  - M2 takes Rs 2,00,000 at two ATMs and sends Rs 1,00,000 to Exchange X.
  - M3, with Rs 3,00,000 of its own, pays Ravi Traders Rs 2,00,000, Galaxy Mobiles Rs 1,20,000 and a Rs 15,000
    salary.

  The tests trace the mules' ledgers with `ripple_core.tracing` and check the PRD's figures: Ravi Traders
  Rs 2,00,000, Galaxy Mobiles Rs 50,000 and the salary Rs 0.

Identifiers come from the simulator's own seeded generator (`identifiers.py`). Each is checked with the
`ripple_core.ids` validators. `ripple_core.ids` generators use `secrets` and can't be reproduced. The messages are
`ripple_core.messages.AccountOpening` and `LedgerPosting`; the declared KYC profile travels as one line of text.
