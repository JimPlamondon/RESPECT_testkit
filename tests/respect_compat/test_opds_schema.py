# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from respect_compat.opds_schema import validate_opds_documents
from respect_compat.resources import resource


REFERENCE = resource("data/fixtures/v1_0/positive/web_reference")


def test_source_locked_opds_schemas_accept_reference_documents():
    descriptor = json.loads((REFERENCE / "descriptor.json").read_text(encoding="utf-8"))
    catalog = json.loads((REFERENCE / "catalog.json").read_text(encoding="utf-8"))
    assert validate_opds_documents([descriptor, catalog]) == []


def test_source_locked_opds_schema_rejects_missing_publication_title():
    descriptor = json.loads((REFERENCE / "descriptor.json").read_text(encoding="utf-8"))
    del descriptor["metadata"]["title"]
    errors = validate_opds_documents([descriptor])
    assert errors
    assert any("title" in error for error in errors)


def test_missing_source_locked_schema_cache_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_opds_documents([], cache=tmp_path)
