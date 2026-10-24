"""Which transactions move cash in or out of the banking system.

A cash deposit comes from the branch counter (source account "CASH..."). Every other cash transaction is a payment
or a withdrawal from the source account. A cash-out is where traceable money leaves for good: a cash withdrawal, a
crypto purchase, or a payment to a known ATM, business-correspondent or crypto off-ramp account. In production the
bank's own list of such terminals and virtual-asset exchange accounts replaces the name prefixes used here.
"""

from __future__ import annotations

from ripple.schema import Rail, Transaction

CASH_SOURCE_PREFIX = "CASH"
CASH_OUT_PREFIXES = ("ATM", "P2P-", "VDA-", "CRYPTO")


def is_cash_deposit(txn: Transaction) -> bool:
    return txn.rail == Rail.CASH and txn.src_account.upper().startswith(CASH_SOURCE_PREFIX)


def is_cash_out(txn: Transaction) -> bool:
    if txn.rail == Rail.CRYPTO or (txn.rail == Rail.CASH and not is_cash_deposit(txn)):
        return True
    return txn.dst_account.upper().startswith(CASH_OUT_PREFIXES)
