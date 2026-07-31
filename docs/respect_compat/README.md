# RESPECT Compatible Test Suite 1.0

The RESPECT Compatible Test Suite applies the canonical RESPECT Compatibility Matrix to one submitted Candidate App, called the `CanApp`. It reports black-box compatibility evidence, does not require CanApp source code, and does not grant trademark, registry, or certification rights.

For AI-operated installation and application, begin with
[`../AI_OPERATOR.md`](../AI_OPERATOR.md). For the end-to-end operator sequence,
see [`../CERTIFICATION_WORKFLOW.md`](../CERTIFICATION_WORKFLOW.md).

The canonical Matrix is package data owned by `respect_compat`; the Test Suite verifies its semantic hash before every run. The historical `compatibility_matrix_v0_1.json` profile is independently consumed and is not canonical Matrix authority.

Provision the exact OPDS (Open Publication Distribution System) and Readium Web Publication Manifest revisions with `respect-standards-bootstrap`. Set `RESPECT_STANDARDS_CACHE` to choose a cache root.

Run `respect-compat --help` or `python -m respect_compat.cli --help` for the supported black-box target forms and output parameters. `--profile` accepts the canonical profile identifiers `PROFILE-WEB`, `PROFILE-NATIVE_ANDROID`, `PROFILE-SUITE_QUALITY`, and `PROFILE-CLAIMED_FUTURE`.

The `--apk-only --apk <path>` target form assesses a raw native Android Candidate App before it has a descriptor or publication server. It binds the exact submitted APK, supplies no invented document, and lets the ordinary Matrix executors report absent discovery and publication behavior alongside static APK findings and blocked runtime prerequisites.

Certification produces a fresh unpredictable scenario nonce. Test and replay modes may accept a deterministic run seed. Applicable rows that cannot be observed fail closed as blocked.

Every run emits the authoritative JSON report, a sanitized evidence manifest, an immutable RESPECT-ification task packet, a text report, and a JUnit test report. The task packet contains only actionable CanApp-owned nonpasses and is the one-way handoff to the optional Kit.

CanApp-owned rows alone determine CanApp compatibility. RESPECT-owned and Test-Suite-owned rows remain separately attributed, and a RESPECT environment defect is never reported as a CanApp defect.

The publisher-owned `PUBLISH-001` and `PUBLISH-002` rows gate the later Foundation registry-publication step without mislabeling missing paperwork or hosting as Candidate App defects. `PUBLISH-003` separately requires Spix to supply the independently source-locked Ed25519 trust anchor. Until that key exists, the Test Suite generates and persistently reuses a testing keypair, exercises the token path with a testing-only authorization when the other exact-build facts are available, and reports `Provisional (RESPECT certification key is testing-only)`. A submission-supplied key cannot establish Spix trust.

Native Android rows that require attributable device behavior use the Test Suite-owned companion and Android Debug Bridge controller documented in [NATIVE_ANDROID_RUNTIME_DRIVER.md](NATIVE_ANDROID_RUNTIME_DRIVER.md). The controller accepts no imported row outcomes and validates its companion build receipt before enabling controlled-runtime evidence.
