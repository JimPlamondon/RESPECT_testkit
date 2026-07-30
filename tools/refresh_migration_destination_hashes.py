#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Refresh post-separation migration destinations without rewriting history."""

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value):
    candidate = dict(value)
    candidate.pop("manifest_hash", None)
    return hashlib.sha256(
        json.dumps(
            candidate,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.repository_root
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        if entry.get("disposition") in {"migrated", "adapted"}:
            destination = root / entry["destination_path"]
            entry["destination_sha256"] = sha256(destination)

    native_by_path = {
        entry["destination_path"]: entry
        for entry in manifest["native_entries"]
        if (root / entry["destination_path"]).is_file()
    }
    old_atomic = "src/respect_compat/data/schemas/atomic_result_v2.schema.json"
    new_atomic = "src/respect_compat/data/schemas/atomic_result_v3.schema.json"
    native_by_path.pop(old_atomic, None)
    native_by_path[new_atomic] = {
        "destination_path": new_atomic,
        "destination_sha256": sha256(root / new_atomic),
        "item_class": "schema",
        "provenance": "post_extraction",
        "reason": (
            "post-separation TestKit atomic-result authority with neutral "
            "platform attribution and no Dossier work artifact"
        ),
    }
    audit = "src/respect_compat/data/matrix/legacy_provenance_audit.json"
    native_by_path[audit] = {
        "destination_path": audit,
        "destination_sha256": sha256(root / audit),
        "item_class": "schema",
        "provenance": "post_extraction",
        "reason": (
            "post-separation frozen audit enforcing the two-origin contract "
            "for new or changed TestKit requirements"
        ),
    }
    for entry in native_by_path.values():
        entry["destination_sha256"] = sha256(
            root / entry["destination_path"]
        )
    manifest["native_entries"] = sorted(
        native_by_path.values(), key=lambda item: item["destination_path"]
    )
    manifest["manifest_hash"] = canonical_hash(manifest)
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
