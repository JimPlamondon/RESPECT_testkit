# RESPECT-ification Kit 1.0

The RESPECT-ification Kit turns immutable, Matrix-addressed Test Suite failures into owner-local repair work. The Test Suite does not require CanApp source code or the Kit.

The Kit does not determine compatibility. A narrow verifier result is always marked `narrow_non_certifying`; a complete selected-profile Test Suite run is the only compatibility oracle.

Run `respect-ification --help` or `python -m respect_ification.cli --help` for the supported `prepare`, `plan`, `driver-plan`, `status`, `record`, `verify`, and `full-test` commands.

Public Prep contains aggregate build-system and language metadata. Optional private Prep contains root-relative source inventory and remains inside the CanApp owner's environment. Neither form can change Matrix requirements, evidence, outcomes, or verdicts.

The planner validates run, Matrix, profile, target, evidence, graph, and content-hash bindings. The append-only repair ledger validates its hash chain and legal state transitions. No command contained in an input artifact is executed.

The `full-test` handback invokes the complete Test Suite and preserves its exit code and verdict without reinterpretation.

When owner-local Candidate App source is available and the work plan contains native Android runtime-gated rows, `driver-plan` inspects that source and generates a row-complete implementation prompt instead of treating the missing runtime capability as terminal. The Test Suite-owned controller remains responsible for all trusted runtime observations; CanApp-side test code may trigger behavior but cannot submit row outcomes.
