# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)


@dataclass(frozen=True)
class CertificationKey:
    private_key: Path
    public_key: Path
    key_id: str
    fingerprint_sha256: str
    provenance: str = "testing_generated"


def _load_private(path: Path) -> Ed25519PrivateKey:
    value = serialization.load_pem_private_key(
        path.read_bytes(),
        password=None,
    )
    if not isinstance(value, Ed25519PrivateKey):
        raise ValueError(
            "testing certification key is not an Ed25519 private key"
        )
    return value


def ensure_testing_certification_key(state_dir: Path) -> CertificationKey:
    state_dir = state_dir.resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    private_path = state_dir / "testing-certification-private.pem"
    public_path = state_dir / "testing-certification-public.pem"
    if not private_path.exists():
        generated = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        try:
            descriptor = os.open(
                private_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(generated)
    os.chmod(private_path, 0o600)
    private_key = _load_private(private_path)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if not public_path.is_file() or public_path.read_bytes() != public_bytes:
        temporary = state_dir / (
            f".testing-certification-public.{os.getpid()}.tmp"
        )
        temporary.write_bytes(public_bytes)
        os.chmod(temporary, 0o644)
        os.replace(temporary, public_path)
    fingerprint = hashlib.sha256(public_bytes).hexdigest()
    return CertificationKey(
        private_key=private_path,
        public_key=public_path,
        key_id=f"respect-testkit-testing-{fingerprint[:16]}",
        fingerprint_sha256=fingerprint,
    )
