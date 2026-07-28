# RESPECT-ification Kit 1.0

The RESPECT-ification Kit turns immutable, Matrix-addressed Test Suite failures into owner-local repair work. The Test Suite does not require CanApp source code or the Kit.

The Kit does not determine compatibility. A narrow verifier result is always marked `narrow_non_certifying`; a complete selected-profile Test Suite run is the only compatibility oracle.

Run `respect-ification --help` or `python -m respect_ification.cli --help` for the supported `prepare`, `plan`, `driver-plan`, `status`, `record`, `verify`, and `full-test` commands.

Public Prep contains aggregate build-system and language metadata. Optional private Prep contains root-relative source inventory and remains inside the CanApp owner's environment. Neither form can change Matrix requirements, evidence, outcomes, or verdicts.

The planner validates run, Matrix, profile, target, evidence, graph, and content-hash bindings. The append-only repair ledger validates its hash chain and legal state transitions. No command contained in an input artifact is executed.

The `full-test` handback invokes the complete Test Suite and preserves its exit code and verdict without reinterpretation.

When owner-local Candidate App source is available and the work plan contains native Android runtime-gated rows, `driver-plan` inspects manifests, build files, lesson-loading seams, lesson content files, launch handling, lifecycle code, and Experience API code. Its generated implementation prompt requires a one-to-one inventory of real lessons, generator-backed OPDS and Readium wrappers, catalog-derived launch URLs, and runtime statements bound to actual lesson facts. A synthetic lesson, placeholder wrapper, marker resource, debug-only completion trigger, or disconnected activity identifier is explicitly forbidden.

The Test Suite-owned controller remains responsible for all trusted runtime observations; CanApp-side test code may drive real user operations but cannot submit row outcomes or manufacture product facts. When an Android Package Kit contains JiMSong assets, the verifier independently compares the hosted catalog and Readium resources with the packaged lesson titles and bytes.
