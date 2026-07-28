# RESPECT Testkit

`RESPECT-testkit` is the standalone distribution for the RESPECT Compatible Test Suite and the RESPECT-ification Kit. The Test Suite evaluates a Candidate App, called a `CanApp`, from black-box evidence without requiring its source code or the Kit. The Kit consumes immutable Test Suite artifacts to support owner-local repair work and never changes or issues compatibility verdicts.

The canonical RESPECT Compatibility Matrix is bundled once as package data owned by `respect_compat`. The historical v0.1 profile is bundled separately as non-canonical profile data.

Install the project or its built wheel, provision the source-locked standards cache with `respect-standards-bootstrap`, and inspect the command interfaces with `respect-compat --help`, `respect-ification --help`, and `respect-matrix-validate --help`.

For repair work with available Candidate App source, use `respect-ification repair-plan` to generate a Kit-time, source-derived repair adapter and implementation prompt. The adapter is format-agnostic Kit scaffolding: it discovers content candidates and implementation seams from the CanApp's own references, then directs durable changes into the CanApp, its build, its tests, and genuinely external services.

Use `respect-ification truth-audit --output <path>` to emit the complete, content-bound disposition of all 84 canonical Matrix rows. Candidate App repair tasks receive row-specific durable implementation and evidence contracts; requirements owned by RESPECT services, the RESPECT launcher, or the Test Suite cannot be reassigned to the Candidate App.

The publication workflow requires a complete, source-digest-bound lesson inventory rather than blanket confirmation of analyzer candidates. Production publication additionally requires the submitted Android Package Kit and live deployed-origin verification; local pack integrity alone is not production verification.

After confirming the real lesson inventory, use `respect-ification publication-manifest` and `publication-pack` to emit a self-contained RESPECT publication with exact lesson resources, descriptor, OPDS catalog, Readium manifests, acquisition pages, covers, Android association, deployment contract, portable server, container recipe, and validation receipt. `publication-serve` provides provisional HTTPS hosting, while `publication-verify` validates the pack locally and can verify every deployed resource and conditional request at an HTTPS origin.

For native Android runtime verification, use `respect-runtime-driver-build` to build the Test Suite-owned companion. The documented runtime interface is in `docs/respect_compat/NATIVE_ANDROID_RUNTIME_DRIVER.md`.

This repository is initially private. Publication, package-index upload, tagging, and visibility changes are outside this extraction.
