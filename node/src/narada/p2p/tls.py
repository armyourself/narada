"""Per-node self-signed TLS material for QUIC.

Each Narada node owns a self-signed certificate used to authenticate
its QUIC endpoint. We use TOFU (trust-on-first-use): a node pins the
peer certificate the first time it connects, and rejects a different
cert on subsequent connections. This is **not** a CA / PKI; real
authentication is the responsibility of the application layer (the
node signatures already cryptographically bind envelopes and acks to a
node identity). The TLS layer exists to keep the wire encrypted and
to give us a place to hang the node id on the QUIC ALPN.

Certificate storage::

    <data_dir>/node_identity/tls_cert.pem
    <data_dir>/node_identity/tls_key.pem

Both files are written with 0600 permissions on POSIX systems.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_NARADA_ALPN = b"narada/1"


@dataclass(frozen=True)
class NodeTlsMaterial:
    """A node's TLS cert + private key, loaded once at startup."""

    certificate: x509.Certificate
    private_key: ec.EllipticCurvePrivateKey
    cert_pem: bytes
    key_pem: bytes

    @property
    def alpn_protocol(self) -> bytes:
        return _NARADA_ALPN


def _paths(data_dir: Path) -> tuple[Path, Path]:
    d = Path(str(data_dir)) / "node_identity"
    return d / "tls_cert.pem", d / "tls_key.pem"


def _generate(common_name: str) -> NodeTlsMaterial:
    """Generate a fresh EC P-256 self-signed cert."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(f"narada://{common_name}")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return NodeTlsMaterial(
        certificate=cert, private_key=key, cert_pem=cert_pem, key_pem=key_pem
    )


def load_or_create(data_dir: Path, *, common_name: Optional[str] = None) -> NodeTlsMaterial:
    """Load the on-disk TLS material or generate fresh and persist."""
    cert_path, key_path = _paths(data_dir)
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    if cert_path.exists() and key_path.exists():
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise ValueError("node TLS key is not EC")
            return NodeTlsMaterial(
                certificate=cert,
                private_key=key,
                cert_pem=cert_path.read_bytes(),
                key_pem=key_path.read_bytes(),
            )
        except (ValueError, OSError):
            # Corrupt file: regenerate.
            pass

    cn = common_name or f"narada-node-{datetime.datetime.now().timestamp():.0f}"
    mat = _generate(cn)
    try:
        cert_path.write_bytes(mat.cert_pem)
        key_path.write_bytes(mat.key_pem)
        import os

        try:
            os.chmod(cert_path, 0o600)
            os.chmod(key_path, 0o600)
        except (OSError, NotImplementedError):
            pass
    except OSError:
        # Best effort: a TLS write failure must not stop the node from
        # starting; the caller can regenerate later.
        pass
    return mat


def fingerprint_pem(cert_pem: bytes) -> str:
    """Return a stable SHA-256 fingerprint of a PEM-encoded certificate."""
    cert = x509.load_pem_x509_certificate(cert_pem)
    return cert.fingerprint(hashes.SHA256()).hex()


__all__ = ["NodeTlsMaterial", "load_or_create", "_NARADA_ALPN", "fingerprint_pem"]