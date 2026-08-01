# Public schemas

Runtime schemas are bundled as package data of their owning package. They are
the structural authority; prose explains their use but does not replace
validation.

## Test Suite schemas

Located under `respect_compat/data/schemas/`:

| Schema | Purpose |
|---|---|
| `compatibility_matrix.schema.json` | Canonical Matrix structure, requirements, applicability, tooling, outcomes, and routing ownership |
| `suite_report_v2.schema.json` | Bound Test Suite report envelope and routed results |
| `atomic_result_v3.schema.json` | Exact owner, verification, observation, workflow, and authorized-artifact enums for one atomic result |
| `promotion_packet_v2.schema.json` | Substitute fidelity, covered and excluded semantics, real dependency, clearance, and rerun |

## RESPECT-ification schemas

Located under `respect_ification/data/schemas/`:

| Schema | Purpose |
|---|---|
| `evidence_manifest.schema.json` | Sanitized evidence handoff |
| `task_packet.schema.json` | Immutable Test Suite-to-Kit CanApp task handoff |
| `public_prep.schema.json` | Non-private source summary |
| `private_prep.schema.json` | Owner-local source inventory and hints |
| `work_plan.schema.json` | Bound, nonnormative local repair plan |
| `ledger_event.schema.json` | One hash-chained repair transition |
| `canapp_lesson_inventory.schema.json` | Owner-confirmed canonical lesson inventory |
| `canapp_lesson_model.schema.json` | Evidence-backed interaction families, classifications, templates, and bindings |
| `canapp_lesson_selection.schema.json` | Exact partial, course, family, or complete-inventory selection |
| `canapp_lesson_run_plan.schema.json` | TestKit/target-bound scenarios and blocking reasons |
| `canapp_lesson_coverage.schema.json` | Separate inventory, modeling, selection, compilation, and execution coverage |
| `canapp_lesson_capability_gaps.schema.json` | Generic missing-mechanism report |
| `canapp_lesson_modeling_packet.schema.json` | Private source-bound AI/human modeling handback |

Publication Pack generation also includes its publication-manifest schema in
the emitted artifact set.

## Version rules

- Current routing-family report, evidence, task, work, and promotion artifacts
  use `2.0.0`.
- Atomic routed results use the v3 schema.
- Prep and ledger artifacts retain their declared 1.x formats.
- Legacy routing artifacts are verification-only and cannot generate new work.
- Never combine files from different generations or handoff identifiers.

Use `jsonschema` Draft 2020-12 validation where a schema is supplied, then run
the owning command's semantic verification. Schema validity alone cannot prove
hash bindings, target identity, source bytes, or certification eligibility.
