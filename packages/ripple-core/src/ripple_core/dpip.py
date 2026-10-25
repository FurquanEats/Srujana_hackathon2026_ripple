"""Keyed identifier hashes for the simulated DPIP (Digital Payment Intelligence Platform).

Banks never send DPIP a raw account number. Each identifier (an account with its IFSC, or a UPI ID) is reduced to an
HMAC-SHA256 under a key the network's members share and the platform cannot reverse without it (PRD P3). The same
identifier always gives the same hash, so a check by one bank matches a signal from another.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path

from ripple_core.messages import AccountRef


def identifier_hashes(key: bytes, ref: AccountRef) -> tuple[str, ...]:
    """One hash per identifier the reference carries, in a fixed order."""
    parts = []
    if ref.account_number is not None:
        parts.append(f"acct:{(ref.ifsc or '').upper()}:{ref.account_number}")
    if ref.vpa is not None:
        parts.append(f"vpa:{ref.vpa.lower()}")
    return tuple(hmac.new(key, p.encode("utf-8"), hashlib.sha256).hexdigest() for p in parts)


def load_key(path: Path) -> bytes:
    """The network's shared hashing key, created on first use beside the other network keys."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="ascii")
    return bytes.fromhex(path.read_text(encoding="ascii").strip())
