"""Signed envelopes for every message between bank nodes and hubs.

An envelope is a compact JWS (RFC 7515) signed with Ed25519 (alg "EdDSA", RFC 8037). Its header names the sender
(`iss`), the intended recipient (`aud`), when it was sealed (`iat`), a random `nonce` and an idempotency key (`idem`).

Opening an envelope checks, in this order: the shape, the algorithm, that the key belongs to the claimed sender,
that the envelope is addressed to us, that it is fresh, the signature, and only then that the nonce is new. The
nonce is recorded after the signature check, so a forger cannot burn real nonces. A sender retrying a request
seals it again with a new nonce and the same idempotency key, and the receiver answers it once.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel

from ripple_core.clock import Clock

TYPE = "ripple+jws"
MAX_SKEW = timedelta(seconds=120)
MAX_ENVELOPE_BYTES = 1_000_000


class SealError(Exception):
    """An envelope that must not be trusted."""


class MalformedEnvelopeError(SealError):
    pass


class UnknownKeyError(SealError):
    pass


class WrongRecipientError(SealError):
    pass


class StaleEnvelopeError(SealError):
    pass


class BadSignatureError(SealError):
    pass


class ReplayedEnvelopeError(SealError):
    pass


@dataclass(frozen=True)
class SigningKey:
    kid: str
    owner: str
    private: Ed25519PrivateKey

    @classmethod
    def generate(cls, kid: str, owner: str) -> SigningKey:
        return cls(kid, owner, Ed25519PrivateKey.generate())

    @classmethod
    def from_pem(cls, kid: str, owner: str, pem: bytes) -> SigningKey:
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("expected an Ed25519 private key")
        return cls(kid, owner, key)

    def private_pem(self) -> bytes:
        return self.private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )

    def public_pem(self) -> bytes:
        return self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )


class Keyring:
    """Public keys we trust, each bound to the one institution allowed to sign with it."""

    def __init__(self) -> None:
        self._keys: dict[str, tuple[str, Ed25519PublicKey]] = {}

    def add(self, kid: str, owner: str, public_pem: bytes) -> None:
        key = serialization.load_pem_public_key(public_pem)
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("expected an Ed25519 public key")
        if kid in self._keys and self._keys[kid][0] != owner:
            raise ValueError(f"key {kid!r} is already bound to {self._keys[kid][0]!r}")
        self._keys[kid] = (owner, key)

    def lookup(self, kid: str) -> tuple[str, Ed25519PublicKey]:
        try:
            return self._keys[kid]
        except KeyError:
            raise UnknownKeyError(f"unknown key {kid!r}") from None


class ReplayGuard(Protocol):
    def remember(self, sender: str, nonce: str, until: datetime) -> bool:
        """Record a nonce; return False if it was already seen from this sender."""
        ...


class MemoryReplayGuard:
    """Nonces seen within the freshness window, kept in memory. Services persist theirs in their own database."""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], datetime] = {}
        self._lock = threading.Lock()

    def remember(self, sender: str, nonce: str, until: datetime) -> bool:
        with self._lock:
            self._seen = {k: v for k, v in self._seen.items() if v > until - 2 * MAX_SKEW}
            if (sender, nonce) in self._seen:
                return False
            self._seen[(sender, nonce)] = until
            return True


@dataclass(frozen=True)
class Opened:
    sender: str
    recipient: str
    sealed_at: datetime
    idempotency_key: str
    payload: dict[str, Any]


def seal(
    payload: BaseModel | dict[str, Any],
    *,
    key: SigningKey,
    recipient: str,
    clock: Clock,
    idempotency_key: str | None = None,
) -> str:
    body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    header = {
        "alg": "EdDSA",
        "typ": TYPE,
        "kid": key.kid,
        "iss": key.owner,
        "aud": recipient,
        "iat": int(clock.now().timestamp()),
        "nonce": secrets.token_urlsafe(18),
        "idem": idempotency_key or secrets.token_urlsafe(18),
    }
    signing_input = f"{_b64(_canonical(header))}.{_b64(_canonical(body))}"
    signature = key.private.sign(signing_input.encode("ascii"))
    return f"{signing_input}.{_b64(signature)}"


def open_sealed(
    envelope: str,
    *,
    keyring: Keyring,
    recipient: str,
    clock: Clock,
    replay: ReplayGuard,
    max_skew: timedelta = MAX_SKEW,
) -> Opened:
    if len(envelope) > MAX_ENVELOPE_BYTES:
        raise MalformedEnvelopeError("envelope too large")
    parts = envelope.split(".")
    if len(parts) != 3:
        raise MalformedEnvelopeError("an envelope has three parts")
    header = _json_part(parts[0], "header")
    body = _json_part(parts[1], "payload")
    for field in ("kid", "iss", "aud", "nonce", "idem"):
        if not isinstance(header.get(field), str) or not header[field]:
            raise MalformedEnvelopeError(f"header field {field!r} missing")
    if header.get("alg") != "EdDSA" or header.get("typ") != TYPE:
        raise MalformedEnvelopeError("unsupported algorithm or type")
    iat = header.get("iat")
    if not isinstance(iat, int) or isinstance(iat, bool):
        raise MalformedEnvelopeError("header field 'iat' missing")

    owner, public_key = keyring.lookup(header["kid"])
    if owner != header["iss"]:
        raise UnknownKeyError(f"key {header['kid']!r} does not belong to {header['iss']!r}")
    if header["aud"] != recipient:
        raise WrongRecipientError(f"envelope is for {header['aud']!r}, not {recipient!r}")
    now = clock.now()
    sealed_at = datetime.fromtimestamp(iat, tz=now.tzinfo)
    if abs(now - sealed_at) > max_skew:
        raise StaleEnvelopeError("envelope is outside the freshness window")
    try:
        public_key.verify(_unb64(parts[2]), f"{parts[0]}.{parts[1]}".encode("ascii"))
    except (InvalidSignature, ValueError) as exc:
        raise BadSignatureError("signature does not verify") from exc
    if not replay.remember(owner, header["nonce"], sealed_at + max_skew):
        raise ReplayedEnvelopeError("this envelope was already received")
    return Opened(owner, recipient, sealed_at, header["idem"], body)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    if not text or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in text
    ):
        raise MalformedEnvelopeError("not base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _json_part(text: str, name: str) -> dict[str, Any]:
    try:
        value = json.loads(_unb64(text))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MalformedEnvelopeError(f"{name} is not JSON") from exc
    if not isinstance(value, dict):
        raise MalformedEnvelopeError(f"{name} must be a JSON object")
    return value
