# RESPECT Testkit

`RESPECT-testkit` is the standalone distribution for the RESPECT Compatible Test Suite and the RESPECT-ification Kit. The Test Suite evaluates a Candidate App, called a `CanApp`, from black-box evidence without requiring its source code or the Kit. The Kit consumes immutable Test Suite artifacts to support owner-local repair work and never changes or issues compatibility verdicts.

The canonical RESPECT Compatibility Matrix is bundled once as package data owned by `respect_compat`. The historical v0.1 profile is bundled separately as non-canonical profile data.

Install the project or its built wheel, provision the source-locked standards cache with `respect-standards-bootstrap`, and inspect the command interfaces with `respect-compat --help`, `respect-ification --help`, and `respect-matrix-validate --help`.

This repository is initially private. Publication, package-index upload, tagging, and visibility changes are outside this extraction.
