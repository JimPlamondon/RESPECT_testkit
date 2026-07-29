#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0
#
"""Validate the canonical RESPECT Compatibility Matrix and evidence index."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .resources import resource

DEFAULT_MATRIX = resource("data/matrix/compatibility_matrix.json")
DEFAULT_INDEX = resource("data/indexes/source_interaction_index.json")
DEFAULT_REPORT = Path.cwd() / "matrix_validation_report.json"
SCHEMA = resource("data/schemas/compatibility_matrix.schema.json")

OWNER_VALUES = {
    "canapp",
    "publisher",
    "spix_foundation",
    "respect_launcher",
    "respect_service",
    "learning_record_store",
    "test_suite",
    "ecosystem_resource",
    "profile_owner",
}
NONEXECUTABLE_IMPLEMENTATION = {
    "claimed_not_implemented",
    "contradicted_by_implementation",
    "not_implemented",
    "unknown",
}
OUTCOMES = {
    "pass",
    "fail",
    "not_applicable",
    "incomplete",
    "deferred",
    "harness_error",
    "blocked",
}
ROW_ID = re.compile(r"^[A-Z][A-Z0-9_-]*-[0-9]{3}$")
FEATURE_ID = re.compile(r"^RCF-[A-Z0-9][A-Z0-9_-]*$")
PROFILE_ID = re.compile(r"^PROFILE-[A-Z0-9][A-Z0-9_-]*$")
FAMILY_ID = re.compile(r"^IF-[A-Z0-9][A-Z0-9_-]*$")
SOURCE_REF_ID = re.compile(r"^SRC-[A-Z0-9][A-Z0-9_-]*$")
CONTRACT_ID = re.compile(r"^SC-[A-Z0-9][A-Z0-9_-]*$")
BINDING_ID = re.compile(r"^BIND-[A-Z0-9][A-Z0-9_-]*$")
EQUIVALENCE_ID = re.compile(r"^EQUIV-[A-Z0-9][A-Z0-9_-]*$")
INTERACTION_ID = re.compile(r"^INT-[A-Z0-9][A-Z0-9_-]*$")
INVENTORY_CLASS_ID = re.compile(r"^DISC-[0-9]{2}$")
INVENTORY_CLASSES = {
    "DISC-01": "CanApp registration and removal",
    "DISC-02": "CanApp descriptor",
    "DISC-03": "Catalog and learning-content discovery",
    "DISC-04": "Publication and resource acquisition",
    "DISC-05": "Launch semantic contract",
    "DISC-06": "Launch bindings",
    "DISC-07": "Hosted web runtime",
    "DISC-08": "Offline availability and caching",
    "DISC-09": "Transport-independent xAPI semantics",
    "DISC-10": "xAPI delivery bindings",
    "DISC-11": "Identity, authentication, authorization, and credentials",
    "DISC-12": "Errors and diagnostics",
    "DISC-13": "Lifecycle and state",
    "DISC-14": "Capability, version, and support status",
    "DISC-15": "Conformance evidence",
    "DISC-16": "Internal implementation evidence",
}


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.metadata: dict[str, Any] = {}

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def warn(self, condition: bool, message: str) -> None:
        if not condition:
            self.warnings.append(message)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def semantic_hash(matrix: dict[str, Any]) -> str:
    payload = copy.deepcopy(matrix)
    payload.pop("semantic_hash", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def require_keys(
    validation: Validation, value: Any, keys: Iterable[str], label: str
) -> None:
    validation.require(isinstance(value, dict), f"{label} must be an object")
    if not isinstance(value, dict):
        return
    for key in keys:
        validation.require(key in value, f"{label} missing required field {key}")


def unique_ids(
    validation: Validation,
    records: Any,
    field: str,
    pattern: re.Pattern[str],
    label: str,
) -> set[str]:
    if not isinstance(records, list):
        validation.errors.append(f"{label} must be an array")
        return set()
    values: list[str] = []
    for number, record in enumerate(records):
        require_keys(validation, record, [field], f"{label}[{number}]")
        if not isinstance(record, dict) or field not in record:
            continue
        value = record[field]
        validation.require(
            isinstance(value, str) and pattern.fullmatch(value) is not None,
            f"{label}[{number}].{field} has invalid identifier {value!r}",
        )
        if isinstance(value, str):
            values.append(value)
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    validation.require(not duplicates, f"{label} has duplicate identifiers: {duplicates}")
    return set(values)


def validate_source_citations(
    validation: Validation,
    citations: Any,
    source_ids: set[str],
    label: str,
) -> None:
    validation.require(isinstance(citations, list), f"{label} must be an array")
    if not isinstance(citations, list):
        return
    for number, citation in enumerate(citations):
        require_keys(
            validation,
            citation,
            ["source_ref", "locator", "evidence"],
            f"{label}[{number}]",
        )
        if not isinstance(citation, dict):
            continue
        source_ref = citation.get("source_ref")
        validation.require(
            source_ref in source_ids,
            f"{label}[{number}] references unknown source {source_ref!r}",
        )
        validation.require(
            isinstance(citation.get("locator"), str) and bool(citation["locator"].strip()),
            f"{label}[{number}] needs an exact locator",
        )


def validate_index(
    validation: Validation,
    index: Any,
    matrix: dict[str, Any],
    source_lock_ids: set[str],
    semantic_contract_ids: set[str],
    binding_ids: set[str],
    feature_ids: set[str],
    row_ids: set[str],
) -> tuple[set[str], dict[str, Any]]:
    require_keys(
        validation,
        index,
        [
            "index_id",
            "index_version",
            "matrix_id",
            "generated_at",
            "source_locks",
            "searches",
            "evidence_items",
            "candidates",
            "rejected_candidates",
            "inventory_classes",
            "interactions",
        ],
        "source_interaction_index",
    )
    if not isinstance(index, dict):
        return set(), {
            "source_to_matrix": "incomplete",
            "matrix_to_source": "incomplete",
            "inventory_status": {},
            "unmapped_interactions": [],
            "unmapped_features": sorted(feature_ids),
            "unmapped_rows": sorted(row_ids),
        }
    validation.require(
        index.get("matrix_id") == matrix.get("matrix_id"),
        "source_interaction_index.matrix_id must match the Matrix",
    )
    validation.require(
        set(index.get("source_locks", [])) == source_lock_ids,
        "source_interaction_index.source_locks must exactly match Matrix source locks",
    )
    evidence_ids = unique_ids(
        validation,
        index.get("evidence_items"),
        "source_ref",
        SOURCE_REF_ID,
        "source_interaction_index.evidence_items",
    )
    for number, item in enumerate(index.get("evidence_items", [])):
        if not isinstance(item, dict):
            continue
        require_keys(
            validation,
            item,
            [
                "source_ref",
                "source_lock_id",
                "evidence_class",
                "locator",
                "observation",
                "disposition",
            ],
            f"source_interaction_index.evidence_items[{number}]",
        )
        validation.require(
            item.get("source_lock_id") in source_lock_ids,
            f"evidence item {item.get('source_ref')} references an unknown source lock",
        )
        validation.require(
            isinstance(item.get("locator"), str) and bool(item["locator"].strip()),
            f"evidence item {item.get('source_ref')} needs an exact locator",
        )
        validation.require(
            isinstance(item.get("observation"), str) and bool(item["observation"].strip()),
            f"evidence item {item.get('source_ref')} needs a source observation",
        )
        validation.require(
            item.get("evidence_class")
            in {
                "accepted_direct_evidence",
                "diagnostic_evidence",
                "rejected_or_partial_evidence",
                "source_observation",
                "orchestration_infrastructure_only",
                "not_relevant_to_matrix",
            },
            f"evidence item {item.get('source_ref')} has invalid evidence_class",
        )

    inventory_ids = unique_ids(
        validation,
        index.get("inventory_classes"),
        "inventory_class_id",
        INVENTORY_CLASS_ID,
        "source_interaction_index.inventory_classes",
    )
    validation.require(
        inventory_ids == set(INVENTORY_CLASSES),
        "source_interaction_index.inventory_classes must contain DISC-01 through DISC-16 exactly once",
    )
    inventory_status: dict[str, str] = {}
    declared_interactions_by_class: dict[str, set[str]] = {}
    for number, item in enumerate(index.get("inventory_classes", [])):
        if not isinstance(item, dict):
            continue
        label = f"source_interaction_index.inventory_classes[{number}]"
        require_keys(
            validation,
            item,
            [
                "inventory_class_id",
                "title",
                "status",
                "inspected_source_areas",
                "interaction_ids",
                "notes",
            ],
            label,
        )
        class_id = item.get("inventory_class_id")
        validation.require(
            item.get("title") == INVENTORY_CLASSES.get(class_id),
            f"{class_id} title does not match the binding discovery manifest",
        )
        validation.require(
            item.get("status")
            in {"not_started", "in_progress", "complete", "no_findings", "blocked"},
            f"{class_id} has invalid inventory status",
        )
        inventory_status[str(class_id)] = str(item.get("status"))
        inspected_areas = item.get("inspected_source_areas")
        validation.require(
            isinstance(inspected_areas, list),
            f"{class_id}.inspected_source_areas must be an array",
        )
        if item.get("status") in {"complete", "no_findings"}:
            validation.require(
                bool(inspected_areas),
                f"{class_id} cannot be complete without inspected source areas",
            )
        declared_interactions_by_class[str(class_id)] = set(item.get("interaction_ids", []))

    interaction_ids = unique_ids(
        validation,
        index.get("interactions"),
        "interaction_id",
        INTERACTION_ID,
        "source_interaction_index.interactions",
    )
    actual_interactions_by_class: dict[str, set[str]] = {
        class_id: set() for class_id in INVENTORY_CLASSES
    }
    mapped_features: set[str] = set()
    mapped_rows: set[str] = set()
    unmapped_interactions: list[str] = []
    unresolved_interactions: list[str] = []
    for number, interaction in enumerate(index.get("interactions", [])):
        if not isinstance(interaction, dict):
            continue
        interaction_id = interaction.get("interaction_id")
        label = f"source interaction {interaction_id}"
        require_keys(
            validation,
            interaction,
            [
                "interaction_id",
                "inventory_class_ids",
                "record_type",
                "source_ref",
                "source_lock_id",
                "locator",
                "symbol",
                "entry_point",
                "branch_predicate",
                "terminal_effect",
                "observable_result",
                "actors",
                "semantic_contract_id",
                "binding_id",
                "feature_ids",
                "row_ids",
                "exclusion",
                "inspection_method",
                "evidence_status",
            ],
            label,
        )
        class_ids = set(interaction.get("inventory_class_ids", []))
        validation.require(
            bool(class_ids) and not (class_ids - inventory_ids),
            f"{label} references unknown or empty inventory classes",
        )
        for class_id in class_ids & inventory_ids:
            actual_interactions_by_class[class_id].add(str(interaction_id))
        validation.require(
            interaction.get("record_type")
            in {
                "production_boundary",
                "test",
                "fixture",
                "requirement_claim",
                "documentation_claim",
                "active_consumer",
                "runtime_observation",
                "standard_clause",
                "owner_decision",
            },
            f"{label} has invalid record_type",
        )
        validation.require(
            interaction.get("source_ref") in evidence_ids,
            f"{label} references unknown source evidence",
        )
        validation.require(
            interaction.get("source_lock_id") in source_lock_ids,
            f"{label} references unknown source lock",
        )
        for field in (
            "locator",
            "symbol",
            "entry_point",
            "branch_predicate",
            "terminal_effect",
            "observable_result",
            "inspection_method",
        ):
            validation.require(
                isinstance(interaction.get(field), str)
                and bool(interaction.get(field, "").strip()),
                f"{label}.{field} must name an explicit value",
            )
        actors = interaction.get("actors")
        validation.require(
            isinstance(actors, list) and bool(actors),
            f"{label}.actors must name at least one actor",
        )
        for actor_number, actor in enumerate(actors or []):
            require_keys(
                validation,
                actor,
                ["actor", "responsibility"],
                f"{label}.actors[{actor_number}]",
            )
        contract_id = interaction.get("semantic_contract_id")
        binding_id = interaction.get("binding_id")
        validation.require(
            contract_id is None or contract_id in semantic_contract_ids,
            f"{label} references unknown semantic contract",
        )
        validation.require(
            binding_id is None or binding_id in binding_ids,
            f"{label} references unknown binding",
        )
        interaction_features = set(interaction.get("feature_ids", []))
        interaction_rows = set(interaction.get("row_ids", []))
        validation.require(
            not (interaction_features - feature_ids),
            f"{label} references unknown Matrix features",
        )
        validation.require(
            not (interaction_rows - row_ids),
            f"{label} references unknown Matrix rows",
        )
        mapped_features.update(interaction_features & feature_ids)
        mapped_rows.update(interaction_rows & row_ids)
        feature_contracts = {
            feature.get("feature_id"): set(feature.get("semantic_contract_ids", []))
            for feature in matrix.get("features", [])
            if isinstance(feature, dict)
        }
        row_contracts = {
            row.get("row_id"): row.get("semantic_contract_id")
            for row in matrix.get("rows", [])
            if isinstance(row, dict)
        }
        for feature_id in interaction_features & feature_ids:
            validation.require(
                contract_id in feature_contracts.get(feature_id, set()),
                f"{label} semantic contract does not match mapped feature {feature_id}",
            )
        for row_id in interaction_rows & row_ids:
            validation.require(
                contract_id == row_contracts.get(row_id),
                f"{label} semantic contract does not match mapped row {row_id}",
            )
        exclusion = interaction.get("exclusion")
        validation.require(
            exclusion is None or isinstance(exclusion, dict),
            f"{label}.exclusion must be null or an object",
        )
        if isinstance(exclusion, dict):
            require_keys(validation, exclusion, ["status", "rationale"], f"{label}.exclusion")
            validation.require(
                exclusion.get("status")
                in {"non_canapp_obligation", "rejected_candidate", "out_of_scope"},
                f"{label}.exclusion has invalid status",
            )
        evidence_status = interaction.get("evidence_status")
        validation.require(
            evidence_status
            in {
                "accepted_source_observation",
                "diagnostic_evidence",
                "rejected_candidate",
                "unresolved",
                "out_of_scope",
            },
            f"{label} has invalid evidence_status",
        )
        if evidence_status == "accepted_source_observation" and not (
            interaction_features or interaction_rows or isinstance(exclusion, dict)
        ):
            unmapped_interactions.append(str(interaction_id))
            validation.errors.append(
                f"{label} is accepted but has no Matrix mapping or explicit exclusion"
            )
        if evidence_status == "unresolved":
            unresolved_interactions.append(str(interaction_id))

    for class_id in sorted(INVENTORY_CLASSES):
        validation.require(
            declared_interactions_by_class.get(class_id, set())
            == actual_interactions_by_class.get(class_id, set()),
            f"{class_id} interaction closure mismatch",
        )

    completed_inventory = all(
        inventory_status.get(class_id) in {"complete", "no_findings"}
        for class_id in INVENTORY_CLASSES
    )
    source_to_matrix_complete = (
        completed_inventory and not unmapped_interactions and not unresolved_interactions
    )
    unmapped_features = sorted(feature_ids - mapped_features)
    unmapped_rows = sorted(row_ids - mapped_rows)
    matrix_to_source_complete = not unmapped_features and not unmapped_rows
    return evidence_ids, {
        "source_to_matrix": "complete" if source_to_matrix_complete else "incomplete",
        "matrix_to_source": "complete" if matrix_to_source_complete else "incomplete",
        "inventory_status": dict(sorted(inventory_status.items())),
        "unmapped_interactions": sorted(unmapped_interactions),
        "unresolved_interactions": sorted(unresolved_interactions),
        "unmapped_features": unmapped_features,
        "unmapped_rows": unmapped_rows,
        "interaction_count": len(interaction_ids),
    }


def validate_matrix(matrix: Any, index: Any) -> Validation:
    validation = Validation()
    require_keys(
        validation,
        matrix,
        [
            "schema_version",
            "matrix_id",
            "matrix_version",
            "generated_at",
            "status",
            "authority_rule",
            "canapp_definition",
            "product_boundary",
            "source_locks",
            "profiles",
            "interface_families",
            "semantic_contracts",
            "bindings",
            "binding_equivalence_groups",
            "features",
            "rows",
            "completeness",
            "blockers",
            "unresolved_questions",
            "semantic_hash",
        ],
        "matrix",
    )
    if not isinstance(matrix, dict):
        return validation

    validation.require(matrix.get("schema_version") == "1.2.0", "unsupported schema_version")
    validation.require(
        matrix.get("status") in {"draft", "incomplete", "ready", "blocked"},
        "matrix.status has an invalid value",
    )
    require_keys(
        validation,
        matrix.get("product_boundary"),
        ["included", "excluded", "failure_attribution_rule"],
        "matrix.product_boundary",
    )

    source_lock_ids = unique_ids(
        validation,
        matrix.get("source_locks"),
        "source_lock_id",
        re.compile(r"^LOCK-[A-Z0-9][A-Z0-9_-]*$"),
        "matrix.source_locks",
    )
    for number, source_lock in enumerate(matrix.get("source_locks", [])):
        require_keys(
            validation,
            source_lock,
            [
                "source_lock_id",
                "name",
                "source_type",
                "repository_or_uri",
                "revision",
                "retrieved_at",
                "rights_status",
                "use",
            ],
            f"matrix.source_locks[{number}]",
        )
        if isinstance(source_lock, dict):
            validation.require(
                isinstance(source_lock.get("repository_or_uri"), str)
                and bool(source_lock["repository_or_uri"].strip()),
                f"source lock {source_lock.get('source_lock_id')} needs a repository_or_uri",
            )
            validation.require(
                isinstance(source_lock.get("revision"), str)
                and bool(source_lock["revision"].strip()),
                f"source lock {source_lock.get('source_lock_id')} needs an immutable revision",
            )
    profile_ids = unique_ids(
        validation,
        matrix.get("profiles"),
        "profile_id",
        PROFILE_ID,
        "matrix.profiles",
    )
    family_ids = unique_ids(
        validation,
        matrix.get("interface_families"),
        "interface_family_id",
        FAMILY_ID,
        "matrix.interface_families",
    )
    feature_ids = unique_ids(
        validation,
        matrix.get("features"),
        "feature_id",
        FEATURE_ID,
        "matrix.features",
    )
    row_ids = unique_ids(
        validation,
        matrix.get("rows"),
        "row_id",
        ROW_ID,
        "matrix.rows",
    )
    semantic_contract_ids = unique_ids(
        validation,
        matrix.get("semantic_contracts"),
        "semantic_contract_id",
        CONTRACT_ID,
        "matrix.semantic_contracts",
    )
    binding_ids = unique_ids(
        validation,
        matrix.get("bindings"),
        "binding_id",
        BINDING_ID,
        "matrix.bindings",
    )
    equivalence_ids = unique_ids(
        validation,
        matrix.get("binding_equivalence_groups"),
        "equivalence_group_id",
        EQUIVALENCE_ID,
        "matrix.binding_equivalence_groups",
    )
    del equivalence_ids
    source_ids, derived_completeness = validate_index(
        validation,
        index,
        matrix,
        source_lock_ids,
        semantic_contract_ids,
        binding_ids,
        feature_ids,
        row_ids,
    )
    validation.metadata["derived_completeness"] = derived_completeness

    binding_contracts: dict[str, set[str]] = {}
    for contract in matrix.get("semantic_contracts", []):
        if not isinstance(contract, dict):
            continue
        contract_id = contract.get("semantic_contract_id")
        require_keys(
            validation,
            contract,
            ["semantic_contract_id", "title", "scope", "source_refs"],
            f"semantic contract {contract_id}",
        )
        unknown_sources = set(contract.get("source_refs", [])) - source_ids
        validation.require(
            not unknown_sources,
            f"semantic contract {contract_id} references unknown evidence {sorted(unknown_sources)}",
        )

    for binding in matrix.get("bindings", []):
        if not isinstance(binding, dict):
            continue
        binding_id = binding.get("binding_id")
        require_keys(
            validation,
            binding,
            [
                "binding_id",
                "title",
                "binding_type",
                "semantic_contract_ids",
                "implementation_status",
                "canapp_visible_scope",
                "internal_details_status",
                "source_refs",
            ],
            f"binding {binding_id}",
        )
        contracts = set(binding.get("semantic_contract_ids", []))
        binding_contracts[str(binding_id)] = contracts
        validation.require(
            bool(contracts) and not (contracts - semantic_contract_ids),
            f"binding {binding_id} references unknown or empty semantic contracts",
        )
        validation.require(
            binding.get("internal_details_status")
            == "diagnostic_unless_direct_dependency",
            f"binding {binding_id} must keep internal details diagnostic unless directly required by a CanApp",
        )
        validation.require(
            not (set(binding.get("source_refs", [])) - source_ids),
            f"binding {binding_id} references unknown evidence",
        )

    for group in matrix.get("binding_equivalence_groups", []):
        if not isinstance(group, dict):
            continue
        group_id = group.get("equivalence_group_id")
        require_keys(
            validation,
            group,
            [
                "equivalence_group_id",
                "title",
                "semantic_contract_id",
                "binding_ids",
                "equivalence_dimensions",
                "test_case_id",
                "current_suite_status",
            ],
            f"binding equivalence group {group_id}",
        )
        contract_id = group.get("semantic_contract_id")
        group_bindings = set(group.get("binding_ids", []))
        validation.require(
            contract_id in semantic_contract_ids,
            f"binding equivalence group {group_id} references an unknown semantic contract",
        )
        validation.require(
            len(group_bindings) >= 2 and not (group_bindings - binding_ids),
            f"binding equivalence group {group_id} references fewer than two known bindings",
        )
        for binding_id in group_bindings & binding_ids:
            validation.require(
                contract_id in binding_contracts.get(binding_id, set()),
                f"binding equivalence group {group_id} includes binding {binding_id} outside semantic contract {contract_id}",
            )

    for profile in matrix.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        require_keys(
            validation,
            profile,
            [
                "profile_id",
                "title",
                "version",
                "lifecycle_status",
                "applicability",
                "interface_family_ids",
                "source_refs",
            ],
            f"profile {profile.get('profile_id')}",
        )
        unknown = set(profile.get("interface_family_ids", [])) - family_ids
        validation.require(
            not unknown,
            f"profile {profile.get('profile_id')} references unknown families {sorted(unknown)}",
        )

    feature_rows: dict[str, set[str]] = {}
    for feature in matrix.get("features", []):
        if not isinstance(feature, dict):
            continue
        feature_id = feature.get("feature_id")
        require_keys(
            validation,
            feature,
            [
                "feature_id",
                "title",
                "interface_family_id",
                "semantic_contract_ids",
                "requirement_owner",
                "claim_sources",
                "implementation_sources",
                "requirement_status",
                "lifecycle_status",
                "implementation_status",
                "support_status",
                "first_applicable_respect_version",
                "last_applicable_respect_version",
                "nonimplementation_reason",
                "nonimplementation_evidence",
                "scope_rationale",
                "testability_status",
                "documentation_status",
                "conformance_disposition",
                "standard_bindings",
                "respect_revision",
                "profile_ids",
                "row_ids",
                "current_suite_mapping",
                "respect_ification_guidance",
            ],
            f"feature {feature_id}",
        )
        validation.require(
            feature.get("interface_family_id") in family_ids,
            f"feature {feature_id} references an unknown interface family",
        )
        feature_contract_ids = set(feature.get("semantic_contract_ids", []))
        validation.require(
            bool(feature_contract_ids)
            and not (feature_contract_ids - semantic_contract_ids),
            f"feature {feature_id} references unknown or empty semantic contracts",
        )
        validation.require(
            feature.get("requirement_owner") in OWNER_VALUES,
            f"feature {feature_id} has an invalid requirement owner",
        )
        validation.require(
            not (set(feature.get("profile_ids", [])) - profile_ids),
            f"feature {feature_id} references an unknown profile",
        )
        declared_rows = set(feature.get("row_ids", []))
        validation.require(
            not (declared_rows - row_ids),
            f"feature {feature_id} references unknown rows {sorted(declared_rows - row_ids)}",
        )
        feature_rows[str(feature_id)] = declared_rows
        validate_source_citations(
            validation, feature.get("claim_sources"), source_ids, f"feature {feature_id}.claim_sources"
        )
        validate_source_citations(
            validation,
            feature.get("implementation_sources"),
            source_ids,
            f"feature {feature_id}.implementation_sources",
        )
        validate_source_citations(
            validation,
            feature.get("nonimplementation_evidence"),
            source_ids,
            f"feature {feature_id}.nonimplementation_evidence",
        )
        implementation_status = feature.get("implementation_status")
        nonimplementation_reason = feature.get("nonimplementation_reason")
        if implementation_status in NONEXECUTABLE_IMPLEMENTATION:
            validation.require(
                not declared_rows,
                f"non-executable feature {feature_id} must not contain executable rows",
            )
            validation.require(
                nonimplementation_reason != "not_applicable",
                f"non-executable feature {feature_id} needs a specific nonimplementation reason",
            )
            validation.require(
                feature.get("testability_status") == "not_executable_current_implementation",
                f"non-executable feature {feature_id} cannot claim executable testability",
            )
            validation.require(
                feature.get("conformance_disposition")
                in {"upstream_gap", "informative", "excluded_as_designed"},
                f"non-executable feature {feature_id} cannot be an active CanApp obligation",
            )
        if nonimplementation_reason == "as_designed":
            validation.require(
                bool(feature.get("nonimplementation_evidence")),
                f"feature {feature_id} uses as_designed without affirmative evidence",
            )
        for binding_number, binding in enumerate(feature.get("standard_bindings", [])):
            require_keys(
                validation,
                binding,
                ["standard", "version", "clause", "source_ref", "invoked_surface"],
                f"feature {feature_id}.standard_bindings[{binding_number}]",
            )
            if isinstance(binding, dict):
                validation.require(
                    binding.get("source_ref") in source_ids,
                    f"feature {feature_id} standard binding references unknown evidence",
                )
                validation.require(
                    bool(feature.get("implementation_sources")),
                    f"feature {feature_id} binds a standard without active implementation evidence",
                )

    actual_rows_by_feature: dict[str, set[str]] = {feature_id: set() for feature_id in feature_ids}
    feature_owner = {
        feature.get("feature_id"): feature.get("requirement_owner")
        for feature in matrix.get("features", [])
        if isinstance(feature, dict)
    }
    for row in matrix.get("rows", []):
        if not isinstance(row, dict):
            continue
        row_id = row.get("row_id")
        feature_id = row.get("feature_id")
        require_keys(
            validation,
            row,
            [
                "row_id",
                "feature_id",
                "title",
                "test_case_ids",
                "failure_classification",
                "semantic_contract_id",
                "binding_id",
                "requirement_statement",
                "requirement_owner",
                "profile_ids",
                "applicability_predicate",
                "interaction",
                "canapp_behavior",
                "external_actor",
                "route_variant",
                "stimulus_sequence",
                "test_action",
                "required_tooling",
                "tooling_health_preconditions",
                "expected_evidence",
                "evidence_attribution",
                "oracles",
                "outcomes",
                "primary_failure_domain",
                "positive_case",
                "negative_case",
                "source_refs",
                "current_suite_status",
                "narrow_verifier",
            ],
            f"row {row_id}",
        )
        validation.require(feature_id in feature_ids, f"row {row_id} has unknown feature {feature_id}")
        test_case_ids = row.get("test_case_ids")
        validation.require(
            isinstance(test_case_ids, list)
            and bool(test_case_ids)
            and len(test_case_ids) == len(set(test_case_ids))
            and all(isinstance(item, str) and item.startswith("TEST-") for item in test_case_ids),
            f"row {row_id} must have one or more unique stable test-case identifiers",
        )
        validation.require(
            row.get("failure_classification")
            in {
                "retryable",
                "terminal",
                "terminal_until_canapp_corrected",
                "unsupported_as_designed",
                "indeterminate",
            },
            f"row {row_id} has an invalid failure classification",
        )
        if feature_id in actual_rows_by_feature:
            actual_rows_by_feature[feature_id].add(str(row_id))
        validation.require(
            row.get("requirement_owner") in OWNER_VALUES,
            f"row {row_id} has an invalid requirement owner",
        )
        validation.require(
            row.get("requirement_owner") == feature_owner.get(feature_id),
            f"row {row_id} owner does not match parent feature {feature_id}",
        )
        contract_id = row.get("semantic_contract_id")
        parent_feature = next(
            (
                feature
                for feature in matrix.get("features", [])
                if isinstance(feature, dict) and feature.get("feature_id") == feature_id
            ),
            {},
        )
        validation.require(
            contract_id in semantic_contract_ids,
            f"row {row_id} references an unknown semantic contract",
        )
        validation.require(
            contract_id in set(parent_feature.get("semantic_contract_ids", [])),
            f"row {row_id} semantic contract is not declared by parent feature {feature_id}",
        )
        binding_id = row.get("binding_id")
        validation.require(
            binding_id is None or binding_id in binding_ids,
            f"row {row_id} references an unknown binding",
        )
        if binding_id is not None:
            validation.require(
                contract_id in binding_contracts.get(binding_id, set()),
                f"row {row_id} binding {binding_id} does not carry semantic contract {contract_id}",
            )
        validation.require(
            not (set(row.get("profile_ids", [])) - profile_ids),
            f"row {row_id} references an unknown profile",
        )
        if row.get("requirement_owner") != "canapp":
            validation.require(
                row.get("primary_failure_domain") != "canapp",
                f"non-CanApp row {row_id} cannot assign its primary failure to the CanApp",
            )
        else:
            validation.require(
                isinstance(row.get("canapp_behavior"), str)
                and bool(row.get("canapp_behavior", "").strip()),
                f"CanApp row {row_id} needs an explicit CanApp behavior",
            )
        require_keys(
            validation,
            row.get("interaction"),
            ["producer", "produced_behavior", "transport", "consumer", "consumed_behavior"],
            f"row {row_id}.interaction",
        )
        require_keys(
            validation,
            row.get("requirement_statement"),
            ["subject", "action", "input", "receiver", "expected_output", "failure_owner"],
            f"row {row_id}.requirement_statement",
        )
        if isinstance(row.get("requirement_statement"), dict):
            for field in ("subject", "action", "input", "receiver", "expected_output"):
                validation.require(
                    isinstance(row["requirement_statement"].get(field), str)
                    and bool(row["requirement_statement"].get(field, "").strip()),
                    f"row {row_id}.requirement_statement.{field} must be explicit",
                )
            validation.require(
                row["requirement_statement"].get("failure_owner")
                == row.get("primary_failure_domain"),
                f"row {row_id} requirement failure owner must equal primary_failure_domain",
            )
        require_keys(
            validation,
            row.get("oracles"),
            ["conformance", "harness_health", "target_attribution", "anti_cheating"],
            f"row {row_id}.oracles",
        )
        require_keys(validation, row.get("outcomes"), OUTCOMES, f"row {row_id}.outcomes")
        if isinstance(row.get("outcomes"), dict):
            for outcome in OUTCOMES:
                value = row["outcomes"].get(outcome)
                require_keys(
                    validation,
                    value,
                    ["condition", "failure_domain"],
                    f"row {row_id}.outcomes.{outcome}",
                )
            fail = row["outcomes"].get("fail")
            if isinstance(fail, dict):
                validation.require(
                    fail.get("failure_domain") == row.get("primary_failure_domain"),
                    f"row {row_id} fail domain must equal primary_failure_domain",
                )
        unknown_sources = set(row.get("source_refs", [])) - source_ids
        validation.require(
            not unknown_sources,
            f"row {row_id} references unknown evidence {sorted(unknown_sources)}",
        )

    for feature_id in sorted(feature_ids):
        validation.require(
            feature_rows.get(feature_id, set()) == actual_rows_by_feature.get(feature_id, set()),
            f"feature-to-row closure mismatch for {feature_id}",
        )

    completeness = matrix.get("completeness")
    require_keys(
        validation,
        completeness,
        [
            "source_to_matrix",
            "matrix_to_source",
            "family_counts",
            "feature_count",
            "row_count",
            "unresolved_count",
            "ready_for_downstream_code",
        ],
        "matrix.completeness",
    )
    if isinstance(completeness, dict):
        validation.require(
            completeness.get("feature_count") == len(feature_ids),
            "completeness.feature_count does not match features",
        )
        validation.require(
            completeness.get("row_count") == len(row_ids),
            "completeness.row_count does not match rows",
        )
        unresolved = len(matrix.get("blockers", [])) + len(matrix.get("unresolved_questions", []))
        validation.require(
            completeness.get("unresolved_count") == unresolved,
            "completeness.unresolved_count does not match open items",
        )
        expected_family_counts = dict(
            sorted(
                Counter(
                    feature.get("interface_family_id")
                    for feature in matrix.get("features", [])
                    if isinstance(feature, dict)
                ).items()
            )
        )
        validation.require(
            completeness.get("family_counts") == expected_family_counts,
            "completeness.family_counts does not match features",
        )
        validation.require(
            completeness.get("source_to_matrix")
            == derived_completeness["source_to_matrix"],
            "completeness.source_to_matrix does not match the source interaction inventory",
        )
        validation.require(
            completeness.get("matrix_to_source")
            == derived_completeness["matrix_to_source"],
            "completeness.matrix_to_source does not match source interaction mappings",
        )
        if completeness.get("ready_for_downstream_code"):
            validation.require(matrix.get("status") == "ready", "ready Matrix must have status ready")
            validation.require(not unresolved, "ready Matrix cannot have unresolved items")
            validation.require(
                completeness.get("source_to_matrix") == "complete"
                and completeness.get("matrix_to_source") == "complete",
                "ready Matrix needs both completeness crosswalks",
            )
            validation.require(
                not derived_completeness["unmapped_interactions"],
                "ready Matrix cannot contain unmapped accepted source interactions",
            )
            validation.require(
                not derived_completeness["unresolved_interactions"],
                "ready Matrix cannot contain unresolved source interactions",
            )
            validation.require(
                not derived_completeness["unmapped_features"]
                and not derived_completeness["unmapped_rows"],
                "ready Matrix cannot contain features or rows without source interaction mappings",
            )
            suite_verdict_rows = {
                row.get("row_id"): row
                for row in matrix.get("rows", [])
                if isinstance(row, dict) and row.get("requirement_owner") == "test_suite"
            }
            validation.require(
                "SUITE-004" in suite_verdict_rows,
                "ready Matrix must define fail-closed handling for non-pass suite outcomes",
            )
            if "SUITE-004" in suite_verdict_rows:
                verdict_text = json.dumps(suite_verdict_rows["SUITE-004"], sort_keys=True)
                for outcome in ("incomplete", "deferred", "harness_error", "blocked"):
                    validation.require(
                        outcome in verdict_text,
                        f"SUITE-004 must address {outcome} without silently certifying",
                    )

    actual_hash = semantic_hash(matrix)
    if matrix.get("semantic_hash") == "pending":
        validation.warn(
            matrix.get("status") == "draft",
            "semantic_hash may be pending only while matrix.status is draft",
        )
    else:
        validation.require(
            matrix.get("semantic_hash") == actual_hash,
            f"semantic_hash mismatch: expected {actual_hash}",
        )
    return validation


def normalized_mutation(
    matrix: dict[str, Any], index: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_matrix = copy.deepcopy(matrix)
    candidate_index = copy.deepcopy(index)
    candidate_matrix["completeness"]["feature_count"] = len(candidate_matrix["features"])
    candidate_matrix["completeness"]["row_count"] = len(candidate_matrix["rows"])
    candidate_matrix["semantic_hash"] = semantic_hash(candidate_matrix)
    return candidate_matrix, candidate_index


def run_mutation_checks(
    matrix: dict[str, Any], index: dict[str, Any]
) -> list[dict[str, Any]]:
    checks: list[tuple[str, Any, str]] = []

    def duplicate_row(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["rows"].append(copy.deepcopy(candidate["rows"][0]))

    checks.append(("duplicate_row_id", duplicate_row, "duplicate identifiers"))

    def missing_source_revision(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["source_locks"][0]["revision"] = ""

    checks.append(
        ("missing_source_lock_revision", missing_source_revision, "immutable revision")
    )

    def missing_evidence_locator(_: dict[str, Any], candidate_index: dict[str, Any]) -> None:
        candidate_index["evidence_items"][0]["locator"] = ""

    checks.append(("missing_evidence_locator", missing_evidence_locator, "exact locator"))

    def orphan_row(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["rows"][0]["feature_id"] = "RCF-NOT-DEFINED"

    checks.append(("orphan_row", orphan_row, "unknown feature"))

    def mismatched_feature_closure(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        feature = next(item for item in candidate["features"] if item["row_ids"])
        feature["row_ids"] = feature["row_ids"][1:]

    checks.append(
        ("mismatched_feature_row_closure", mismatched_feature_closure, "closure mismatch")
    )

    def misattribute_non_canapp(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        row = next(
            item for item in candidate["rows"] if item["requirement_owner"] != "canapp"
        )
        row["primary_failure_domain"] = "canapp"
        row["outcomes"]["fail"]["failure_domain"] = "canapp"

    checks.append(
        (
            "non_canapp_owner_blames_canapp",
            misattribute_non_canapp,
            "cannot assign its primary failure",
        )
    )

    def missing_oracle(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        del candidate["rows"][0]["oracles"]["conformance"]

    checks.append(("missing_required_oracle", missing_oracle, "missing required field"))

    def missing_test_case_id(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["rows"][0]["test_case_ids"] = []

    checks.append(
        (
            "testable_row_without_test_case_id",
            missing_test_case_id,
            "stable test-case identifiers",
        )
    )

    def invalid_failure_classification(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["rows"][0]["failure_classification"] = "sometimes"

    checks.append(
        (
            "row_without_failure_retryability",
            invalid_failure_classification,
            "invalid failure classification",
        )
    )

    def promote_unimplemented(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        feature = next(
            item
            for item in candidate["features"]
            if item["implementation_status"] == "claimed_not_implemented"
        )
        feature["testability_status"] = "executable_now"
        feature["conformance_disposition"] = "required_canapp"

    checks.append(
        (
            "unimplemented_feature_promoted_to_active",
            promote_unimplemented,
            "cannot claim executable testability",
        )
    )

    def unsupported_as_designed(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        feature = next(
            item
            for item in candidate["features"]
            if item["nonimplementation_reason"] == "as_designed"
        )
        feature["nonimplementation_evidence"] = []

    checks.append(
        (
            "as_designed_without_evidence",
            unsupported_as_designed,
            "uses as_designed without affirmative evidence",
        )
    )

    def non_executable_with_row(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        feature = next(
            item
            for item in candidate["features"]
            if item["implementation_status"] == "claimed_not_implemented"
        )
        feature["row_ids"] = [candidate["rows"][0]["row_id"]]

    checks.append(
        (
            "non_executable_feature_contains_row",
            non_executable_with_row,
            "must not contain executable rows",
        )
    )

    def standard_without_implementation(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        feature = next(item for item in candidate["features"] if item["standard_bindings"])
        feature["implementation_sources"] = []

    checks.append(
        (
            "standard_binding_without_active_interaction",
            standard_without_implementation,
            "without active implementation evidence",
        )
    )

    def remove_fail_closed_rule(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["status"] = "ready"
        candidate["completeness"]["ready_for_downstream_code"] = True
        candidate["completeness"]["source_to_matrix"] = "complete"
        candidate["completeness"]["matrix_to_source"] = "complete"
        candidate["rows"] = [
            row for row in candidate["rows"] if row["row_id"] != "SUITE-004"
        ]
        for feature in candidate["features"]:
            feature["row_ids"] = [
                row_id for row_id in feature["row_ids"] if row_id != "SUITE-004"
            ]

    checks.append(
        (
            "hidden_nonpass_path_can_certify",
            remove_fail_closed_rule,
            "must define fail-closed handling",
        )
    )

    def remove_inventory_class(_: dict[str, Any], candidate_index: dict[str, Any]) -> None:
        candidate_index["inventory_classes"] = candidate_index["inventory_classes"][1:]

    checks.append(
        (
            "missing_required_discovery_class",
            remove_inventory_class,
            "must contain DISC-01 through DISC-16",
        )
    )

    def add_unmapped_interaction(
        candidate: dict[str, Any], candidate_index: dict[str, Any]
    ) -> None:
        interaction_id = "INT-MUTATION-UNMAPPED"
        source_ref = candidate_index["evidence_items"][0]["source_ref"]
        source_lock_id = candidate_index["evidence_items"][0]["source_lock_id"]
        candidate_index["interactions"].append(
            {
                "interaction_id": interaction_id,
                "inventory_class_ids": ["DISC-01"],
                "record_type": "production_boundary",
                "source_ref": source_ref,
                "source_lock_id": source_lock_id,
                "locator": "mutation fixture locator",
                "symbol": "MutationFixture.unmapped",
                "entry_point": "Mutation fixture entry",
                "branch_predicate": "Mutation fixture branch",
                "terminal_effect": "Mutation fixture terminal effect",
                "observable_result": "Mutation fixture observable result",
                "actors": [
                    {
                        "actor": "Mutation fixture actor",
                        "responsibility": "Expose an intentionally unmapped accepted interaction.",
                    }
                ],
                "semantic_contract_id": "SC-REGISTRATION",
                "binding_id": None,
                "feature_ids": [],
                "row_ids": [],
                "exclusion": None,
                "inspection_method": "Validator mutation fixture",
                "evidence_status": "accepted_source_observation",
            }
        )
        candidate_index["inventory_classes"][0]["interaction_ids"].append(interaction_id)

    checks.append(
        (
            "accepted_interaction_without_matrix_mapping",
            add_unmapped_interaction,
            "accepted but has no Matrix mapping or explicit exclusion",
        )
    )

    def mismatched_interaction_contract(
        candidate: dict[str, Any], candidate_index: dict[str, Any]
    ) -> None:
        interaction = next(item for item in candidate_index["interactions"] if item["row_ids"])
        interaction["semantic_contract_id"] = next(
            contract["semantic_contract_id"]
            for contract in candidate["semantic_contracts"]
            if contract["semantic_contract_id"] != interaction["semantic_contract_id"]
        )

    checks.append(
        (
            "interaction_contract_mismatches_mapped_row",
            mismatched_interaction_contract,
            "semantic contract does not match mapped",
        )
    )

    def remove_row_semantic_contract(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        del candidate["rows"][0]["semantic_contract_id"]

    checks.append(
        (
            "row_without_semantic_contract",
            remove_row_semantic_contract,
            "missing required field semantic_contract_id",
        )
    )

    def incompatible_row_binding(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        row = next(item for item in candidate["rows"] if item["semantic_contract_id"] == "SC-XAPI")
        row["binding_id"] = "BIND-LAUNCH-ANDROID-INTENT"

    checks.append(
        (
            "binding_outside_semantic_contract",
            incompatible_row_binding,
            "does not carry semantic contract",
        )
    )

    def incomplete_equivalence_group(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["binding_equivalence_groups"][0]["binding_ids"] = [
            candidate["binding_equivalence_groups"][0]["binding_ids"][0]
        ]

    checks.append(
        (
            "equivalence_group_missing_binding",
            incomplete_equivalence_group,
            "fewer than two known bindings",
        )
    )

    def promote_internal_binding_details(candidate: dict[str, Any], _: dict[str, Any]) -> None:
        candidate["bindings"][0]["internal_details_status"] = "canapp_requirement"

    checks.append(
        (
            "internal_detail_promoted_without_dependency",
            promote_internal_binding_details,
            "must keep internal details diagnostic",
        )
    )

    results: list[dict[str, Any]] = []
    for name, mutate, expected_error in checks:
        candidate_matrix, candidate_index = normalized_mutation(matrix, index)
        mutate(candidate_matrix, candidate_index)
        candidate_matrix["completeness"]["feature_count"] = len(
            candidate_matrix["features"]
        )
        candidate_matrix["completeness"]["row_count"] = len(candidate_matrix["rows"])
        candidate_matrix["semantic_hash"] = semantic_hash(candidate_matrix)
        validation = validate_matrix(candidate_matrix, candidate_index)
        matched = any(expected_error in error for error in validation.errors)
        results.append(
            {
                "name": name,
                "passed": matched,
                "expected_error": expected_error,
                "observed_errors": validation.errors,
            }
        )
    return results


def build_report(
    matrix: dict[str, Any],
    validation: Validation,
    mutation_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    features = matrix.get("features", [])
    rows = matrix.get("rows", [])
    derived_completeness = validation.metadata.get("derived_completeness", {})
    return {
        "report_id": "respect-compatibility-matrix-validation",
        "report_version": "1.0.0",
        "matrix_id": matrix.get("matrix_id"),
        "matrix_version": matrix.get("matrix_version"),
        "matrix_semantic_hash": semantic_hash(matrix),
        "generated_at": matrix.get("generated_at"),
        "valid": not validation.errors,
        "ready_for_downstream_code": bool(
            not validation.errors
            and matrix.get("completeness", {}).get("ready_for_downstream_code")
        ),
        "counts": {
            "source_locks": len(matrix.get("source_locks", [])),
            "profiles": len(matrix.get("profiles", [])),
            "interface_families": len(matrix.get("interface_families", [])),
            "features": len(features),
            "rows": len(rows),
            "semantic_contracts": len(matrix.get("semantic_contracts", [])),
            "bindings": len(matrix.get("bindings", [])),
            "binding_equivalence_groups": len(
                matrix.get("binding_equivalence_groups", [])
            ),
            "blockers": len(matrix.get("blockers", [])),
            "unresolved_questions": len(matrix.get("unresolved_questions", [])),
        },
        "feature_counts_by_owner": dict(
            sorted(Counter(item.get("requirement_owner") for item in features).items())
        ),
        "feature_counts_by_implementation": dict(
            sorted(Counter(item.get("implementation_status") for item in features).items())
        ),
        "row_counts_by_suite_status": dict(
            sorted(Counter(item.get("current_suite_status") for item in rows).items())
        ),
        "family_coverage": matrix.get("completeness", {}).get("family_counts", {}),
        "source_interaction_coverage": derived_completeness,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "mutation_checks": mutation_checks or [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_json(SCHEMA)
        matrix = load_json(args.matrix)
        index = load_json(args.index)
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    validation = validate_matrix(matrix, index)
    mutation_checks = run_mutation_checks(matrix, index) if args.self_test else []
    mutation_failures = [
        check["name"] for check in mutation_checks if not check["passed"]
    ]
    if mutation_failures:
        validation.errors.append(
            f"validator mutation checks failed: {mutation_failures}"
        )
    report = build_report(matrix, validation, mutation_checks)
    if args.write_report:
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for warning in validation.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in validation.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(
        json.dumps(
            {
                "valid": report["valid"],
                "ready_for_downstream_code": report["ready_for_downstream_code"],
                "errors": len(validation.errors),
                "warnings": len(validation.warnings),
                "features": report["counts"]["features"],
                "rows": report["counts"]["rows"],
                "semantic_hash": report["matrix_semantic_hash"],
                "mutation_checks": len(mutation_checks),
            },
            sort_keys=True,
        )
    )
    if validation.errors:
        return 1
    if args.require_ready and not report["ready_for_downstream_code"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
