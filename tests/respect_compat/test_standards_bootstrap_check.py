# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib

import pytest

from respect_compat import standards_bootstrap


def _tree_hash(path):
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        digest.update(str(item.relative_to(path)).encode())
        if item.is_file():
            digest.update(item.read_bytes())
    return digest.hexdigest()


def test_standards_bootstrap_check_is_read_only_and_fail_closed(
    tmp_path, monkeypatch
):
    revisions = {}
    for name, (_, revision) in standards_bootstrap.SOURCES.items():
        checkout = tmp_path / name
        (checkout / ".git").mkdir(parents=True)
        (checkout / "schema").mkdir()
        (checkout / "schema" / "synthetic.schema.json").write_text("{}")
        revisions[checkout] = revision

    calls = []

    def read_only_git(*args, cwd=None):
        calls.append((args, cwd))
        assert args == ("rev-parse", "HEAD")
        return revisions[cwd]

    monkeypatch.setattr(standards_bootstrap, "git", read_only_git)
    before = _tree_hash(tmp_path)

    assert (
        standards_bootstrap.main(
            ["--cache", str(tmp_path), "--check"]
        )
        == 0
    )
    assert _tree_hash(tmp_path) == before
    assert len(calls) == len(standards_bootstrap.SOURCES)

    revisions[tmp_path / "opds"] = "0" * 40
    with pytest.raises(RuntimeError, match="revision mismatch"):
        standards_bootstrap.main(["--cache", str(tmp_path), "--check"])
