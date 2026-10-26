"""Create the local network's certificate authority, TLS certificates and message-signing keys.

Every service and client gets its own TLS certificate (for mutual TLS) and its own Ed25519 signing key. The public
signing keys go into one keyring, each bound to its owner, which every service loads.
"""

from __future__ import annotations

import ipaddress
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ripple_core.network import Network
from ripple_core.signing import SigningKey
from ripple_service.config import CLIENTS, Paths

VALIDITY = timedelta(days=365)


def parties(network: Network) -> list[str]:
    return [m.id for m in network.members] + list(CLIENTS)


def create_all(network: Network, paths: Paths, *, force: bool = False) -> list[Path]:
    if paths.ca_cert.exists() and not force:
        raise FileExistsError(f"{paths.home} already has certificates; pass --force to replace them")
    now = datetime.now(UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ripple local network CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + VALIDITY)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    written = [_write(paths.ca_cert, ca_cert.public_bytes(serialization.Encoding.PEM), secret=False)]
    keyring = []
    for party in parties(network):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, party)]))
            .issuer_name(ca_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + VALIDITY)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
                ),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        key_pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        written.append(
            _write(paths.tls_cert(party), cert.public_bytes(serialization.Encoding.PEM), secret=False)
        )
        written.append(_write(paths.tls_key(party), key_pem, secret=True))
        signing = SigningKey.generate(f"{party}-1", party)
        written.append(_write(paths.signing_key(party), signing.private_pem(), secret=True))
        keyring.append(
            {"kid": signing.kid, "owner": party, "public_pem": signing.public_pem().decode("ascii")}
        )
    written.append(_write(paths.keyring, json.dumps(keyring, indent=2).encode("utf-8"), secret=False))
    return written


def _write(path: Path, data: bytes, *, secret: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if secret:
        os.chmod(path, 0o600)  # owner-only where the OS supports it; .ripple/ is never committed
    return path
