"""Reproducible identifiers for the simulator.

`ripple_core.ids` generates references with the `secrets` module, as a real bank must. The simulator needs the
same seed to give the same month, so it builds identifiers from its own seeded generator and checks each one with
the `ripple_core.ids` validators. Every identifier is unique within a run.
"""

from __future__ import annotations

import random
import string
from collections.abc import Callable

from ripple_core import ids


class SeededIds:
    def __init__(self, rng: random.Random, seed: int = 0) -> None:
        if seed < 0:
            raise ValueError("the seed must not be negative")
        self._rng = rng
        self._seed = seed
        self._used: set[str] = set()

    def _digits(self, n: int) -> str:
        return "".join(self._rng.choice(string.digits) for _ in range(n))

    def _fresh(self, build: Callable[[], str], valid: Callable[[str], bool] | None = None) -> str:
        for _ in range(100):
            value = build()
            if value in self._used:
                continue
            if valid is not None and not valid(value):
                raise ValueError(f"generated an invalid identifier: {value!r}")
            self._used.add(value)
            return value
        raise RuntimeError("could not find a fresh identifier")

    def rrn(self) -> str:
        return self._fresh(lambda: self._rng.choice("123456789") + self._digits(11), ids.is_rrn)

    def neft_utr(self, bank_code: str) -> str:
        return self._fresh(lambda: bank_code + "N" + self._digits(11), ids.is_neft_utr)

    def rtgs_utr(self, bank_code: str) -> str:
        return self._fresh(lambda: bank_code + "R" + self._digits(17), ids.is_rtgs_utr)

    def internal_reference(self, bank_code: str) -> str:
        return self._fresh(lambda: bank_code + "I" + self._digits(12))

    def ifsc(self, bank_code: str) -> str:
        return self._fresh(lambda: bank_code + "0" + self._digits(6), ids.is_ifsc)

    def account_number(self) -> str:
        return self._fresh(lambda: self._rng.choice("123456789") + self._digits(13))

    def ack_number(self, channel: ids.ComplaintChannel) -> str:
        first = "2" if channel is ids.ComplaintChannel.NCRP else "3"
        return self._fresh(lambda: first + self._digits(13), ids.is_ncrp_ack)

    def vpa(self, name: str, handle: str) -> str:
        """A UPI ID such as `arjunmondal7042@bkbb`: the name, the seed, then 3 digits.

        Nodes keep UPI IDs unique, and with the seed in them two seeds never make the same one, so several seeds
        can be posted to one network.
        """
        base = "".join(c for c in name.lower() if c.isascii() and c.isalpha())[:12] or "user"
        return self._fresh(lambda: f"{base}{self._seed}{self._digits(3)}@{handle}", ids.is_vpa)

    def atm_id(self, bank_code: str) -> str:
        return self._fresh(lambda: f"{bank_code}{self._digits(4)}")

    def merchant_id(self) -> str:
        return self._fresh(lambda: self._digits(15))

    def crypto_address(self) -> str:
        return self._fresh(lambda: "0x" + "".join(self._rng.choice("0123456789abcdef") for _ in range(40)))
