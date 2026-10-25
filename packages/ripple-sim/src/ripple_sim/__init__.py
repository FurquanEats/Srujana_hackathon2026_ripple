"""Ripple's payment network simulator.

It plays every bank customer in the simulated network: it opens accounts and posts each payment to the ledgers of
the institutions involved, so every institution keeps only its own ledger, as real banks do. A payment between two
institutions is two postings with the same `Payment`: a debit at the payer's institution and a credit at the payee's.

All randomness comes from one seeded generator, so a seed always gives the same month.
"""
