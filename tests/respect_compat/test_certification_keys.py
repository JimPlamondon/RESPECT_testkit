# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import stat

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from respect_compat.certification_keys import ensure_testing_certification_key


def test_testing_certification_key_is_generated_once_and_reused(tmp_path):
    first = ensure_testing_certification_key(tmp_path)
    private_before = first.private_key.read_bytes()
    public_before = first.public_key.read_bytes()

    second = ensure_testing_certification_key(tmp_path)

    assert second == first
    assert second.private_key.read_bytes() == private_before
    assert second.public_key.read_bytes() == public_before
    assert stat.S_IMODE(second.private_key.stat().st_mode) == 0o600
    loaded = serialization.load_pem_public_key(public_before)
    assert isinstance(loaded, Ed25519PublicKey)


def test_testing_certification_key_has_stable_testing_only_identity(tmp_path):
    key = ensure_testing_certification_key(tmp_path)

    assert key.provenance == "testing_generated"
    assert key.key_id.startswith("respect-testkit-testing-")
    assert len(key.fingerprint_sha256) == 64
