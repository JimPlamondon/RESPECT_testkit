# RESPECT-ification Kit 1.0

The RESPECT-ification Kit turns immutable, Matrix-addressed Test Suite failures into owner-local repair work. The Test Suite does not require CanApp source code or the Kit.

The Kit does not determine compatibility. A narrow verifier result is always marked `narrow_non_certifying`; a complete selected-profile Test Suite run is the only compatibility oracle.

The Kit's `full-test` command preserves the Test Suite's approval and structured provisions unchanged. A repaired CanApp whose applicable rows pass on an emulator or local Hypertext Transfer Protocol Secure publication is reported truthfully as Provisional with explicit reasons, affected rows, existing evidence, clearance actions, rerun scope, and responsible party; the Kit does not turn those environmental provisions into false CanApp failures.

Run `respect-ification --help` or `python -m respect_ification.cli --help` for the supported repair, Publication Pack, verification, serving, and full-test commands.

Public Prep contains aggregate build-system and language metadata. Optional private Prep contains root-relative source inventory and remains inside the CanApp owner's environment. Neither form can change Matrix requirements, evidence, outcomes, or verdicts.

The planner validates run, Matrix, profile, target, evidence, graph, and content-hash bindings. The append-only repair ledger validates its hash chain and legal state transitions. No command contained in an input artifact is executed.

The `full-test` handback invokes the complete Test Suite and preserves its exit code and verdict without reinterpretation.

When owner-local Candidate App source is available, `repair-plan` creates two owner-local artifacts: a structured Kit-time repair adapter and a source-derived implementation prompt. The general analyzer follows the CanApp's own file references and common build, loading, selection, completion, launch, lifecycle, and Experience API seams. It does not encode any Candidate App's proprietary lesson format.

Use `--source-root` for the repository or source collection and, when the CanApp is one project inside it, use `--canapp-root` for that project's relative path. The analyzer scopes product-code signals to the CanApp while following its explicit references to content stored elsewhere in the source collection.

The generated adapter is scaffolding, not a production runtime component. The repair prompt directs durable changes into normal CanApp code and build logic, requires a verified inventory of real selectable lessons, and requires truthful OPDS (Open Publication Distribution System) and Readium artifacts derived from that inventory. Provisional hosting may serve those real artifacts but may not simulate CanApp behavior.

The source analyzer distinguishes build-embedded lesson payloads, embedded loading, remote acquisition, catalog discovery, and bounded caching. When ordinary lessons are embedded or an external acquisition path is incomplete, the generated adapter requires the CanApp to remove ordinary lesson payloads from its installable artifact, discover lightweight publication metadata, download only the selected lesson, validate response status, media type, publication identity, and declared integrity, and retain acquired lessons in a bounded persistent cache with offline reuse and deterministic eviction. The acquisition contract remains content-format agnostic; proprietary parsing remains normal CanApp-owned production code.

The Publication Pack workflow makes the external RESPECT surface deployable without teaching the Kit a proprietary lesson format. `publication-manifest` combines the repair adapter's source-derived lesson candidates with the owner facts that cannot be inferred honestly: stable identifiers, localized title, application package, public and launch paths, native media type, and lesson identifier namespace. Because analyzer candidates are evidence rather than a declared inventory, the command requires explicit `--confirm-all-candidates` acknowledgement after the repair implementer traces the real selector and loader. It refuses candidates without a source-derived title rather than inventing one.

`publication-pack` takes that normalized manifest plus the chosen HTTPS origin, real signing-certificate fingerprint or Android Package Kit, and provisional or production classification. When given an Android Package Kit, the Kit extracts its signer fingerprint and rejects a package identifier that differs from the publication manifest. It emits a self-contained directory with a static `public` tree, CanApp descriptor, OPDS catalog, one Readium wrapper and acquisition page per lesson, exact native lesson bytes, content-derived or owner-supplied covers, Android Digital Asset Links association, integrity declarations, media-type map, cache-validator contract, standalone reference server, container recipe, and content-bound receipt.

Production generation rejects Internet Protocol addresses, local hostnames, debug-signer classification, and omitted signer classification. Provisional generation permits local origins and debug signers but records that status in the deployment metadata and receipt. Neither mode claims control of a hostname or signing key that the owner did not supply.

`publication-serve` serves a pack with exact declared media types, content lengths, `Last-Modified`, content-derived entity tags, and conditional `304 Not Modified` responses. Supplying a certificate and key enables local Transport Layer Security; production may instead terminate Transport Layer Security at an owner-controlled ingress while serving the emitted static tree unchanged. The included container recipe runs the same portable reference server.

`publication-verify` first verifies every emitted artifact, catalog-to-publication-to-resource relationship, exact lesson bytes, integrity declaration, media type, package association, signer fingerprint, origin binding, and receipt hash. With `--deployed-origin`, it additionally retrieves every public resource over HTTPS, compares the served bytes with the pack, verifies response media types and lengths, and requires cache validators plus successful conditional requests. `--ca-cert` permits a provisionally trusted local certificate without weakening production verification.

The unchanged Test Suite remains content-format agnostic. Its runtime controller derives acquisition from the selected catalog publication, binds the selected activity to that publication, observes real runtime behavior and Experience API statements, and rejects owner-authored outcomes. Candidate App-specific continuity is established by production code and production-owned tests generated during repair, not by teaching the Test Suite a proprietary format.
