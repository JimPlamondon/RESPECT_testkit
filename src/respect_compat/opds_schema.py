# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


OPDS_REVISION = "8fda670fc72f110abcf68ad5d26e99ecfeeabf03"
READIUM_REVISION = "655ee4bcea7f63e1226f166f6b128d9bea6c655b"


def default_standards_cache() -> Path:
    configured = os.environ.get("RESPECT_STANDARDS_CACHE")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "respect-compatible-test-suite" / "standards"
    )


def _revision(path: Path) -> str:
    head = (path / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref = path / ".git" / head[5:]
        return ref.read_text(encoding="utf-8").strip()
    return head


def _schemas(cache: Path) -> Dict[str, Dict[str, Any]]:
    roots = {
        cache / "opds": OPDS_REVISION,
        cache / "readium-webpub": READIUM_REVISION,
    }
    schemas: Dict[str, Dict[str, Any]] = {}
    for root, expected_revision in roots.items():
        if not (root / ".git").exists():
            raise FileNotFoundError(root)
        observed_revision = _revision(root)
        if observed_revision != expected_revision:
            raise ValueError(
                f"source-lock mismatch for {root.name}: "
                f"expected {expected_revision}, observed {observed_revision}"
            )
        schema_root = root / "schema"
        for path in sorted(schema_root.rglob("*.schema.json")):
            schema = _python_regex_schema(
                json.loads(path.read_text(encoding="utf-8"))
            )
            schema_id = schema.get("$id")
            if isinstance(schema_id, str):
                schemas[schema_id] = schema
            if root.name == "opds":
                schemas[f"https://specs.opds.io/schema/{path.name}"] = schema
            else:
                schemas[
                    "https://readium.org/webpub-manifest/schema/"
                    + path.relative_to(schema_root).as_posix()
                ] = schema
    return schemas


def _python_regex_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_python_regex_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "pattern" and isinstance(item, str):
            result[key] = re.sub(r"\(\?<[^>]+>", "(?:", item)
        elif key == "patternProperties" and isinstance(item, dict):
            result[key] = {
                re.sub(r"\(\?<[^>]+>", "(?:", pattern): _python_regex_schema(
                    schema
                )
                for pattern, schema in item.items()
            }
        else:
            result[key] = _python_regex_schema(item)
    return result


def validate_opds_documents(
    documents: List[Dict[str, Any]],
    cache: Optional[Path] = None,
) -> List[str]:
    try:
        from jsonschema import Draft7Validator
        from referencing import Registry, Resource
    except ImportError as error:
        raise RuntimeError("jsonschema dependency is unavailable") from error
    store = _schemas(cache or default_standards_cache())
    registry = Registry().with_resources(
        (uri, Resource.from_contents(schema))
        for uri, schema in store.items()
    )
    errors: List[str] = []
    publication_schema = store[
        "https://specs.opds.io/schema/publication.schema.json"
    ]
    feed_schema = store["https://specs.opds.io/schema/feed.schema.json"]
    publication_validator = Draft7Validator(
        publication_schema,
        registry=registry,
    )
    feed_validator = Draft7Validator(
        feed_schema,
        registry=registry,
    )
    for index, document in enumerate(documents):
        if isinstance(document.get("publications"), list):
            errors.extend(
                f"document[{index}].feed:{item.json_path}:{item.message}"
                for item in feed_validator.iter_errors(document)
            )
        else:
            errors.extend(
                f"document[{index}].publication:{item.json_path}:{item.message}"
                for item in publication_validator.iter_errors(document)
            )
    return sorted(errors)
