"""Which bank holds an account, so a hold plan knows which liens this bank places itself and which go to another
bank through CFCFRMS.

A real deployment reads the account's bank from the payment message (its IFSC). In the India simulator, people and
shops bank with us, and accounts opened for a scam (mules, collectors, scam accounts) are spread across us and two
other banks, so a hold plan shows both kinds of hold. IBM AML account IDs carry their bank code ("070:8000A1B2").
"""

from __future__ import annotations

import zlib

OWN = "This bank"
OTHERS = ("Bank B", "Bank C")
SCAM_PREFIXES = ("MULE", "COLL", "NEW", "SCAM")


def bank_of(account: str) -> str:
    if ":" in account:
        return f"Bank {account.split(':', 1)[0]}"
    if account.upper().startswith(SCAM_PREFIXES):
        pick = zlib.crc32(account.encode()) % 3
        return OWN if pick == 0 else OTHERS[pick - 1]
    return OWN
