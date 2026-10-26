import json
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec

from netharness import ROOT
from ripple_cli import certs
from ripple_cli.main import command_for, main
from ripple_core.network import load_network
from ripple_service.config import Paths, load_keyring, load_signing_key


def test_certs_cover_every_party_and_chain_to_the_ca(tmp_path: Path) -> None:
    network = load_network(ROOT / "network.toml")
    paths = Paths(tmp_path / ".ripple")

    certs.create_all(network, paths)

    ca = x509.load_pem_x509_certificate(paths.ca_cert.read_bytes())
    ca_key = ca.public_key()
    assert isinstance(ca_key, ec.EllipticCurvePublicKey)
    for party in certs.parties(network):
        cert = x509.load_pem_x509_certificate(paths.tls_cert(party).read_bytes())
        assert cert.issuer == ca.subject
        cert.verify_directly_issued_by(ca)
        assert load_signing_key(paths, party).owner == party
    owners = {e["owner"] for e in json.loads(paths.keyring.read_text(encoding="utf-8"))}
    assert owners == set(certs.parties(network))
    assert load_keyring(paths).lookup("bank-b-1")[0] == "bank-b"
    with pytest.raises(FileExistsError):
        certs.create_all(network, paths)
    certs.create_all(network, paths, force=True)


def test_services_require_client_certificates(tmp_path: Path) -> None:
    network = load_network(ROOT / "network.toml")
    command = command_for(network.get("bank-b"), Paths(tmp_path))
    assert command[command.index("--ssl-cert-reqs") + 1] == "2"
    assert "ripple_node.app:create_app" in command
    assert "ripple_hubs.cfcfrms:create_app" in command_for(network.get("cfcfrms"), Paths(tmp_path))


def test_up_refuses_to_start_without_certificates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "network.toml").write_text(
        (ROOT / "network.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv("RIPPLE_ROOT", str(tmp_path))
    assert main(["up"]) == 1
    assert main(["certs"]) == 0
    assert main(["certs"]) == 1
