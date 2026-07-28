# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from respect_compat.handoff import canonical_hash


IGNORED_DIRS = {
    ".git",
    ".gradle",
    ".idea",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
SECRET_NAMES = {
    "." + "env",
    "id_" + "rsa",
    "id_" + "ed25519",
}
SECRET_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
LANGUAGES = {
    ".c": "C",
    ".cpp": "C++",
    ".java": "Java",
    ".js": "JavaScript",
    ".kt": "Kotlin",
    ".py": "Python",
    ".rs": "Rust",
    ".ts": "TypeScript",
}
BUILD_FILES = {
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "Cargo.toml": "Cargo",
    "package.json": "npm",
    "pom.xml": "Maven",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
}
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{8,}"
)


def _inventory(root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[str]]:
    files = []
    languages: Dict[str, int] = {}
    build_systems = set()
    for current, dirs, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            item for item in dirs if item not in IGNORED_DIRS
        )
        for directory in list(dirs):
            path = current_path / directory
            if path.is_symlink():
                raise ValueError(f"symlink escape risk: {path.relative_to(root)}")
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError(f"symlink escape risk: {relative}")
            if name in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES:
                raise ValueError(f"secret-bearing path cannot be inventoried: {relative}")
            size = path.stat().st_size
            if size <= 1_000_000 and path.suffix.lower() in {
                ".json", ".kt", ".py", ".rs", ".toml", ".txt", ".xml", ".yaml", ".yml"
            }:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = ""
                if SECRET_PATTERN.search(text):
                    raise ValueError(f"secret-like value detected: {relative}")
            language = LANGUAGES.get(path.suffix.lower())
            if language:
                languages[language] = languages.get(language, 0) + 1
            if name in BUILD_FILES:
                build_systems.add(BUILD_FILES[name])
            files.append(
                {
                    "path": relative,
                    "size": size,
                    "language": language,
                }
            )
    return files, dict(sorted(languages.items())), sorted(build_systems)


def generate_prep(
    source_root: Path,
    target_digest: str,
    profile_id: str,
    include_private: bool = False,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source root must be a directory")
    files, languages, build_systems = _inventory(root)
    public_core = {
        "artifact_type": "respect_ification_public_prep",
        "format_version": "1.0.0",
        "target_digest": target_digest,
        "profile_id": profile_id,
        "declared_capabilities": [],
        "repository_summary": {
            "file_count": len(files),
            "languages": languages,
            "build_systems": build_systems,
        },
    }
    bundle_id = canonical_hash(public_core)
    public = {**public_core, "prep_bundle_id": bundle_id}
    public["semantic_hash"] = canonical_hash(public, ("semantic_hash",))
    private = None
    if include_private:
        private = {
            "artifact_type": "respect_ification_private_prep",
            "format_version": "1.0.0",
            "prep_bundle_id": bundle_id,
            "public_semantic_hash": public["semantic_hash"],
            "target_digest": target_digest,
            "profile_id": profile_id,
            "source_root_name": root.name,
            "source_inventory": files,
            "row_mappings": {},
            "build_entry_points": [
                item["path"]
                for item in files
                if Path(item["path"]).name in BUILD_FILES
            ],
            "owner_notes": [],
        }
        private["semantic_hash"] = canonical_hash(private, ("semantic_hash",))
    return public, private


def validate_prep_pair(
    public: Dict[str, Any], private: Optional[Dict[str, Any]] = None
) -> List[str]:
    errors = []
    if public.get("artifact_type") != "respect_ification_public_prep":
        errors.append("invalid public Prep artifact type")
    if public.get("semantic_hash") != canonical_hash(
        public, ("semantic_hash",)
    ):
        errors.append("public Prep semantic hash mismatch")
    forbidden = {"source_inventory", "row_mappings", "source_root", "source_root_name"}
    if forbidden.intersection(public):
        errors.append("public Prep contains private fields")
    if private is not None:
        if private.get("artifact_type") != "respect_ification_private_prep":
            errors.append("invalid private Prep artifact type")
        if private.get("semantic_hash") != canonical_hash(
            private, ("semantic_hash",)
        ):
            errors.append("private Prep semantic hash mismatch")
        for key in ("prep_bundle_id", "target_digest", "profile_id"):
            if private.get(key) != public.get(key):
                errors.append(f"Prep {key} binding mismatch")
        if private.get("public_semantic_hash") != public.get("semantic_hash"):
            errors.append("private Prep public hash binding mismatch")
        for paths in private.get("row_mappings", {}).values():
            for value in paths:
                path = Path(value)
                if path.is_absolute() or ".." in path.parts:
                    errors.append("private Prep contains unsafe source path")
    return sorted(set(errors))


def write_prep(
    public: Dict[str, Any],
    public_path: Path,
    private: Optional[Dict[str, Any]] = None,
    private_path: Optional[Path] = None,
) -> None:
    errors = validate_prep_pair(public, private)
    if errors:
        raise ValueError(f"invalid Prep Packet: {errors}")
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if private is not None:
        if private_path is None:
            raise ValueError("private output path is required")
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_text(
            json.dumps(private, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        private_path.chmod(0o600)
