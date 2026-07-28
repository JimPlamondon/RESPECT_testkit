# RESPECT-ification Kit 1.0

The RESPECT-ification Kit turns immutable, Matrix-addressed Test Suite failures into owner-local repair work. The Test Suite does not require CanApp source code or the Kit.

The Kit does not determine compatibility. A narrow verifier result is always marked `narrow_non_certifying`; a complete selected-profile Test Suite run is the only compatibility oracle.

Run `respect-ification --help` or `python -m respect_ification.cli --help` for the supported `prepare`, `plan`, `repair-plan`, `status`, `record`, `verify`, and `full-test` commands.

Public Prep contains aggregate build-system and language metadata. Optional private Prep contains root-relative source inventory and remains inside the CanApp owner's environment. Neither form can change Matrix requirements, evidence, outcomes, or verdicts.

The planner validates run, Matrix, profile, target, evidence, graph, and content-hash bindings. The append-only repair ledger validates its hash chain and legal state transitions. No command contained in an input artifact is executed.

The `full-test` handback invokes the complete Test Suite and preserves its exit code and verdict without reinterpretation.

When owner-local Candidate App source is available, `repair-plan` creates two owner-local artifacts: a structured Kit-time repair adapter and a source-derived implementation prompt. The general analyzer follows the CanApp's own file references and common build, loading, selection, completion, launch, lifecycle, and Experience API seams. It does not encode any Candidate App's proprietary lesson format.

Use `--source-root` for the repository or source collection and, when the CanApp is one project inside it, use `--canapp-root` for that project's relative path. The analyzer scopes product-code signals to the CanApp while following its explicit references to content stored elsewhere in the source collection.

The generated adapter is scaffolding, not a production runtime component. The repair prompt directs durable changes into normal CanApp code and build logic, requires a verified inventory of real selectable lessons, and requires truthful OPDS (Open Publication Distribution System) and Readium artifacts derived from that inventory. Provisional hosting may serve those real artifacts but may not simulate CanApp behavior.

The source analyzer distinguishes build-embedded lesson payloads, embedded loading, remote acquisition, catalog discovery, and bounded caching. When ordinary lessons are embedded or an external acquisition path is incomplete, the generated adapter requires the CanApp to remove ordinary lesson payloads from its installable artifact, discover lightweight publication metadata, download only the selected lesson, validate response status, media type, publication identity, and declared integrity, and retain acquired lessons in a bounded persistent cache with offline reuse and deterministic eviction. The acquisition contract remains content-format agnostic; proprietary parsing remains normal CanApp-owned production code.

The unchanged Test Suite remains content-format agnostic. Its runtime controller derives acquisition from the selected catalog publication, binds the selected activity to that publication, observes real runtime behavior and Experience API statements, and rejects owner-authored outcomes. Candidate App-specific continuity is established by production code and production-owned tests generated during repair, not by teaching the Test Suite a proprietary format.
