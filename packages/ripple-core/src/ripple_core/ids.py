"""Indian payment and case identifiers: validation and, for the simulator, generation.

Formats follow what banks and NCRP use in practice:

- NCRP acknowledgement: 14 digits, starting with 2 for a complaint filed on cybercrime.gov.in and 3 for one taken
  on the 1930 helpline (MHA SOP for NCRP-CFCFRMS, paras 6.1 and 6.2).
- UPI and IMPS reference (RRN): 12 digits.
- NEFT UTR: 16 characters, the sending bank's 4-letter code, "N", then 11 digits.
- RTGS UTR: 22 characters, the sending bank's 4-letter code, "R", then 17 digits.
- IFSC: 4 letters, a zero, then 6 letters or digits.
- UPI ID (VPA): a handle before "@" and a provider after it.
- GSTIN: 15 characters ending in a check character computed with the GST network's mod-36 scheme.
- Indian mobile number: 10 digits starting with 6 to 9.
"""

from __future__ import annotations

import re
import secrets
from enum import StrEnum

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

_NCRP_ACK = re.compile(r"^[23]\d{13}$")
_RRN = re.compile(r"^\d{12}$")
_NEFT_UTR = re.compile(r"^[A-Z]{4}N\d{11}$")
_RTGS_UTR = re.compile(r"^[A-Z]{4}R\d{17}$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_VPA = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")
_GSTIN_SHAPE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_MOBILE = re.compile(r"^[6-9]\d{9}$")


class ComplaintChannel(StrEnum):
    NCRP = "ncrp"
    HELPLINE_1930 = "1930"


def is_ncrp_ack(value: str) -> bool:
    return bool(_NCRP_ACK.match(value))


def complaint_channel(ack: str) -> ComplaintChannel:
    """Which channel an NCRP acknowledgement number came from."""
    if not is_ncrp_ack(ack):
        raise ValueError(f"not an NCRP acknowledgement number: {ack!r}")
    return ComplaintChannel.NCRP if ack[0] == "2" else ComplaintChannel.HELPLINE_1930


def is_rrn(value: str) -> bool:
    return bool(_RRN.match(value))


def is_neft_utr(value: str) -> bool:
    return bool(_NEFT_UTR.match(value))


def is_rtgs_utr(value: str) -> bool:
    return bool(_RTGS_UTR.match(value))


def is_ifsc(value: str) -> bool:
    return bool(_IFSC.match(value))


def is_vpa(value: str) -> bool:
    return bool(_VPA.match(value))


def is_mobile(value: str) -> bool:
    return bool(_MOBILE.match(value))


def gstin_check_char(first14: str) -> str:
    """The 15th character of a GSTIN, from its first 14."""
    if len(first14) != 14 or any(c not in GSTIN_CHARS for c in first14):
        raise ValueError(f"need 14 GSTIN characters, got {first14!r}")
    total = 0
    for i, c in enumerate(first14):
        product = GSTIN_CHARS.index(c) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return GSTIN_CHARS[(36 - total % 36) % 36]


def is_gstin(value: str) -> bool:
    """A GSTIN with the right shape and a correct check character."""
    return bool(_GSTIN_SHAPE.match(value)) and gstin_check_char(value[:14]) == value[14]


# Generators for the simulator. They use the `secrets` module so that generated references are unpredictable,
# like real ones; the simulator's own randomness, which must be reproducible, lives in ripple-sim.


def _digits(n: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(n))


def new_ncrp_ack(channel: ComplaintChannel) -> str:
    return ("2" if channel is ComplaintChannel.NCRP else "3") + _digits(13)


def new_rrn() -> str:
    return _digits(12)


def new_neft_utr(bank_code: str) -> str:
    return _bank_code(bank_code) + "N" + _digits(11)


def new_rtgs_utr(bank_code: str) -> str:
    return _bank_code(bank_code) + "R" + _digits(17)


def _bank_code(bank_code: str) -> str:
    if not re.fullmatch(r"[A-Z]{4}", bank_code):
        raise ValueError(f"bank code must be 4 capital letters, got {bank_code!r}")
    return bank_code
