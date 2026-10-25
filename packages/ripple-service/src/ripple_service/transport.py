"""Signed requests between services.

Every call carries a JSON body `{"envelope": "<signed envelope>"}` and gets one back. The receiver checks that the
envelope is genuine, fresh, addressed to it, not a replay, and from a sender allowed to call that route. Between
processes the calls travel over HTTPS with mutual TLS against the project's certificate authority.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable, Collection
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict

from ripple_core.clock import Clock
from ripple_core.network import Network
from ripple_core.signing import (
    Keyring,
    Opened,
    ReplayGuard,
    SealError,
    SigningKey,
    UnknownKeyError,
    open_sealed,
    seal,
)
from ripple_service.config import Paths

Post = Callable[[str, str, dict[str, Any]], dict[str, Any]]  # (member id, path, JSON body) -> JSON body


class RemoteError(ConnectionError):
    """Another member refused a request with an HTTP error; `status` and `detail` say why."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", "")
    except (ValueError, AttributeError):
        detail = ""
    return str(detail)[:300] or response.reason_phrase


class Sealed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope: str


class Envelopes:
    def __init__(self, key: SigningKey, keyring: Keyring, clock: Clock, replay: ReplayGuard) -> None:
        self.key = key
        self.keyring = keyring
        self.clock = clock
        self.replay = replay

    @property
    def party(self) -> str:
        return self.key.owner

    def open(self, body: Sealed, allowed: Collection[str]) -> Opened:
        """Open a request, turning every failure into a 401 or 403 that reveals nothing about why."""
        try:
            opened = open_sealed(
                body.envelope,
                keyring=self.keyring,
                recipient=self.party,
                clock=self.clock,
                replay=self.replay,
            )
        except UnknownKeyError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown sender") from exc
        except SealError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "envelope rejected") from exc
        if opened.sender not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "sender may not call this route")
        return opened

    def seal(
        self, payload: BaseModel | dict[str, Any], to: str, idempotency_key: str | None = None
    ) -> Sealed:
        envelope = seal(
            payload, key=self.key, recipient=to, clock=self.clock, idempotency_key=idempotency_key
        )
        return Sealed(envelope=envelope)


class Courier:
    """Sends a signed request to another member and opens its signed reply."""

    def __init__(self, envelopes: Envelopes, post: Post) -> None:
        self.envelopes = envelopes
        self.post = post

    def call(
        self, to: str, path: str, payload: BaseModel | dict[str, Any], idempotency_key: str | None = None
    ) -> Opened:
        body = self.envelopes.seal(payload, to, idempotency_key)
        reply = Sealed.model_validate(self.post(to, path, body.model_dump()))
        try:
            return open_sealed(
                reply.envelope,
                keyring=self.envelopes.keyring,
                recipient=self.envelopes.party,
                clock=self.envelopes.clock,
                replay=self.envelopes.replay,
            )
        except SealError as exc:
            raise ConnectionError(f"{to} sent a reply that does not verify") from exc


def mtls_post(network: Network, paths: Paths, party: str, timeout: float = 15.0) -> Post:
    """A `Post` that calls members over HTTPS, presenting `party`'s client certificate."""
    context = ssl.create_default_context(cafile=str(paths.ca_cert))
    context.load_cert_chain(str(paths.tls_cert(party)), str(paths.tls_key(party)))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    client = httpx.Client(verify=context, timeout=timeout)

    def post(to: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = client.post(network.get(to).url + path, json=body)
        except httpx.HTTPError as exc:
            raise ConnectionError(f"{to}{path} failed: {exc}") from exc
        if response.is_error:
            raise RemoteError(response.status_code, _detail(response))
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ConnectionError(f"{to}{path} sent a reply that is not JSON") from exc
        return data

    return post
