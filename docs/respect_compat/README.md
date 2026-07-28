# RESPECT Compatible Test Suite 1.0

The RESPECT Compatible Test Suite applies the canonical RESPECT Compatibility Matrix to one submitted Candidate App, called the `CanApp`. It reports black-box compatibility evidence, does not require CanApp source code, and does not grant trademark, registry, or certification rights.

The canonical Matrix is package data owned by `respect_compat`; the Test Suite verifies its semantic hash before every run. The historical `compatibility_matrix_v0_1.json` profile is independently consumed and is not canonical Matrix authority.

Provision the exact OPDS (Open Publication Distribution System) and Readium Web Publication Manifest revisions with `respect-standards-bootstrap`. Set `RESPECT_STANDARDS_CACHE` to choose a cache root.

Run `respect-compat --help` or `python -m respect_compat.cli --help` for the supported black-box target forms and output parameters. `--profile` accepts the canonical profile identifiers `PROFILE-WEB`, `PROFILE-NATIVE_ANDROID`, `PROFILE-SUITE_QUALITY`, and `PROFILE-CLAIMED_FUTURE`.

Certification produces a fresh unpredictable scenario nonce. Test and replay modes may accept a deterministic run seed. Applicable rows that cannot be observed fail closed as blocked.

Every run emits the authoritative JSON report, a sanitized evidence manifest, an immutable RESPECT-ification task packet, a text report, and a JUnit test report. The task packet contains only actionable CanApp-owned nonpasses and is the one-way handoff to the optional Kit.

CanApp-owned rows alone determine CanApp compatibility. RESPECT-owned and Test-Suite-owned rows remain separately attributed, and a RESPECT environment defect is never reported as a CanApp defect.
