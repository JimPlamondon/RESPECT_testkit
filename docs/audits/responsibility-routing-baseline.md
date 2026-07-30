# Responsibility-routing baseline

SPDX-FileCopyrightText: 2026 Jim Plamondon

SPDX-License-Identifier: Apache-2.0

> **Historical, non-authoritative baseline.** This document records the
> combined-tree state before the TestKit / Upgrade Dossier separation.
> References below to Dossier routing, packets, or eligibility are preserved
> only as historical evidence and do not govern the current TestKit.

## Scope and provenance

This audit records the read-only Phase 0 baseline for the responsibility-routing
and Upgrade Dossier foundation. It was taken from commit
`bd799274c17a52348b7dd79eb21b733a2d5a880f` on a clean `main` worktree before
creating task branch `codex/respect-routing-dossier`. Repository-local hooks were
active through `core.hooksPath=.githooks`; both `pre-commit` and `commit-msg`
were executable.

The RESPECT authorization gate remained closed. No RESPECT checkout was read,
built, run, changed, or contacted.

## Baseline verification

The repository did not have `python` or its console scripts on `PATH`. A
temporary Python 3.9 virtual environment outside the repository was therefore
installed from the checkout. Commands below use `$PY` for that environment and
`$CACHE`/`$TMP` for temporary directories outside the repository.

| Check | Result |
|---|---|
| `$PY -m pytest -q` | green: 159 passed |
| `RESPECT_STANDARDS_CACHE=$CACHE respect-standards-bootstrap` | green: both source-locked standards provisioned |
| `respect-matrix-validate --self-test --require-ready` | green: 45 features, 87 rows, 21 mutation checks |
| `$PY -m build` | green: sdist and wheel built |
| `reuse lint` | green: 186/186 files compliant |
| `git diff --check` | green |

`respect-standards-bootstrap --check` did not exist and was intentionally not
run at baseline.

## Volatile-fact dispositions

| Fact | Disposition and locator |
|---|---|
| Bootstrap exposes `--cache`, not `--check` | **confirmed** — `standards_bootstrap.main` |
| `CertificationProvision.responsible_party` is an unconstrained string | **confirmed** — `models.CertificationProvision` |
| No typed `respect_platform*` responsible-party value exists | **confirmed** — `models.RequirementOwner` and repository symbol search |
| Verdict reduction considers only CanApp-owned rows | **confirmed** — `engine.reduce_verdict` |
| `MatrixRowResult` conflates ownership, result, failure domain, and repair guidance | **confirmed** — `models.MatrixRowResult` |
| Matrix schema lacks typed control-owner and responsible-party fields | **confirmed** — compatibility Matrix schema `$defs.owner` and row definition |
| Provision derivation does not consume row results | **confirmed** — `provisions.derive_provisions` and `engine.execute` |
| Kit actionability uses generic state membership plus CanApp owner | **confirmed** — `handoff.ACTIONABLE_STATES` and `build_handoff` |
| Handoff artifacts use `1.0.0`; Suite report is unversioned | **confirmed** — `handoff.build_handoff` and `report.suite_json_payload` |
| JUnit collapses every non-pass/non-fail result to skipped | **confirmed** — `report.write_suite_reports` |
| CLI exit meanings are locally encoded | **confirmed** — `cli.main` |
| Android runtime and engine mint different scenario identities | **confirmed** — `cli.main` passes a fresh token to `run_native_android_runtime`; `engine.execute` derives another value from `run_id` |
| `environment_executor` consumes metadata but no production provider writes it | **confirmed** — `executors.environment_executor`; sole non-Matrix repository match |
| `SUITE-003/004/005` return literal success | **confirmed** — `executors.suite_executor` |
| `PROFILE-SUITE_QUALITY` exists and selects Suite rows | **confirmed** — 7 selected rows, all seven returned pass in the diagnostic |
| `_read_url` directly reads `file:` paths | **confirmed** — `executors._read_url` |
| Applicability prose is not evaluated | **confirmed** — `matrix_runtime.CompatibilityMatrix.selected_rows` |
| No Dossier package exists | **confirmed** — package inventory |
| Python floor and CI coverage | **confirmed** — `requires-python >=3.9`; CI matrix 3.9 and 3.13 |
| Publication and Suite CLI shapes | **confirmed** through installed console-script `--help` |
| Matrix row count | **confirmed** structurally: 87 unique row IDs |
| RESPECT-owned partition | **corrected/confirmed** structurally: 20 rows, 8 `respect_launcher` and 12 `respect_service`; all lack a production observation provider |
| Challenge partition | **corrected**: all 87 rows declare legacy `scenario_nonce`; 52 additionally declare `challenge`, so the baseline is not an exclusive 52/35 split |
| Rowless upstream-gap features | **confirmed** structurally: 13 |
| RESPECT version fields | **corrected**: all 45 features contain revision and first-applicable fields; every last-applicable field is null; runtime code does not enforce the spine |
| Target digest covers every later-consumed byte | **unverifiable — not confirmed within reading budget**; smallest next check is a byte-by-byte target-loader and executor consumption trace |

## Controlled diagnostics

### `PROFILE-WEB`

A provisional publication pack was generated outside the repository from
non-sensitive synthetic inputs shaped like the tracked publication-pack test.
It preserved `/example`, was served only at
`https://localhost:<ephemeral-port>/example/descriptor.json`, used a one-run
certificate with a `localhost` subject alternative name, and was trusted
through `--ca-cert`. TLS verification was never disabled.

The Suite command exited `2` in test mode with:

- 20 pass;
- 37 blocked;
- 9 not applicable;
- 3 incomplete.

All 18 RESPECT-owned rows selected by `PROFILE-WEB` were blocked because no
controlled RESPECT environment observation existed. The local server log
showed only expected `/example` publication resources and one successful
conditional request. Temporary key, certificate, pack, output, and diagnostic
reports were kept outside the repository and are not evidence for
certification.

### `PROFILE-SUITE_QUALITY`

The profile selected `SUITE-001` through `SUITE-007` and returned seven passes.
The production implementation shows that `SUITE-003`, `SUITE-004`, and
`SUITE-005` pass from literal `True` values. This is a minimized reproduction
of the false-assurance baseline, not proof of Suite quality.

### Challenge and unsafe-file reproductions

- Challenge mismatch: `cli.main` creates the Android runtime token at the call
  to `run_native_android_runtime`; `engine.execute` then creates a different
  run-derived scenario value. There is no parameter that threads the first
  value into engine execution.
- Unsafe file read: `executors._read_url` converts any `file:` URL to a path
  and calls `read_bytes()` without proving that the path is inside a trusted
  fixture root. The reproduction was limited to source inspection and tracked
  fixtures; no arbitrary local file or private service was probed.

## Complete row routing inventory

The live Matrix does not yet contain the six independent typed dimensions.
This inventory records the baseline owner plus the Phase 0 expected routing
classification. Actual observed result and workflow disposition remain
classifier-derived at execution time.

### CanApp artifact control

- **Dimensions:** requirement owner `canapp`; control owner
  `canapp_artifact`; responsible party `canapp_artifact_owner`; verification
  mode fixture, static, substitute, or real according to the executor.
- **Route:** only an attributable implementation violation may create exactly
  one Kit task. Positive qualified substitute evidence may create a promotion
  packet. No Dossier is permitted.
- **Rows (57):** `ANDROID-001`, `ANDROID-002`, `AUTH-001`, `AUTH-003`,
  `DESC-001`, `DESC-002`, `DESC-003`, `DESC-004`, `DESC-005`, `HTTP-001`,
  `HTTP-002`, `HTTP-003`, `HTTP-004`, `HTTP-005`, `LAUNCH-003`,
  `LAUNCH-004`, `LAUNCH-005`, `LAUNCH-006`, `LAUNCH-007`,
  `LIFECYCLE-001`, `MANIFEST-001`, `MANIFEST-002`, `MANIFEST-003`,
  `MANIFEST-004`, `MANIFEST-005`, `MANIFEST-006`, `MANIFEST-007`,
  `MANIFEST-008`, `MANIFEST-009`, `OPDS-001`, `OPDS-002`, `OPDS-003`,
  `OPDS-004`, `OPDS-005`, `OPDS-006`, `OPDS-007`, `OPDS-008`,
  `OPDS-009`, `OPDS-010`, `OPDS-011`, `XAPI-001`, `XAPI-003`,
  `XAPI-004`, `XAPI-005`, `XAPI-006`, `XAPI-007`, `XAPI-008`,
  `XAPI-009`, `XAPI-010`, `XAPI-011`, `XAPI-013`, `XAPI-014`,
  `XAPI-015`, `XAPI-016`, `XAPI-017`, `XAPI-018`, `XAPI-019`.

### RESPECT platform control

- **Dimensions:** requirement owner remains the Matrix's
  `respect_launcher` or `respect_service`; control owner `respect_platform`;
  responsible party `respect_platform_team`; baseline verification mode
  `unavailable`.
- **Route:** all are currently TestKit Capability Gaps because the required
  observer/provider is absent before observation. No target blame,
  platform-gap packet, or Dossier is permitted. A Dossier becomes eligible
  only after signed, independently attributable, pinned real-build evidence.
- **Rows (20):** `AUTH-002`, `LAUNCH-001`, `LAUNCH-002`, `LAUNCH-009`,
  `OFFLINE-001`, `OFFLINE-002`, `OFFLINE-003`, `REG-001`, `REG-002`,
  `REG-003`, `REG-004`, `REG-005`, `WEB-001`, `WEB-002`, `WEB-003`,
  `WEB-004`, `WEB-005`, `XAPI-002`, `XAPI-012`, `XAPI-020`.

Partition at baseline:

- qualifying observation already present: none;
- missing observer/provider: all 20;
- specification blocked before observation: none established by executable
  Matrix data;
- Dossier eligible: none.

### TestKit control

- **Dimensions:** requirement owner `test_suite`; control owner `testkit`;
  responsible party `testkit_team`; required verification mode
  `production_meta_test`.
- **Route:** a prescribed positive and isolated-negative production-path
  meta-test gates certification-capable execution. No Kit task or Dossier.
- **Rows (7):** `SUITE-001`, `SUITE-002`, `SUITE-003`, `SUITE-004`,
  `SUITE-005`, `SUITE-006`, `SUITE-007`.

### Publisher and Spix control

- **Publisher rows:** `PUBLISH-001`, `PUBLISH-002`; requirement/control owner
  and responsible party `publisher`; route to publisher clearance and
  promotion evidence, never Kit repair or Dossier.
- **Spix row:** `PUBLISH-003`; requirement/control owner and responsible party
  `spix_foundation`; route to trust-anchor clearance and promotion evidence,
  never Kit repair or Dossier.

## Rowless upstream-gap work

The 13 confirmed feature-addressed items are:

`RCF-CANAPP-COMPLETION-CLAIM`, `RCF-CREDENTIAL-LIFECYCLE-GAPS`,
`RCF-LAUNCH-OUTCOME-GAPS`, `RCF-LIFECYCLE-STATE-GAPS`, `RCF-LTI-AGS`,
`RCF-LTI-LAUNCH`, `RCF-OAUTH`, `RCF-OFFLINE-FAILURE-GAPS`,
`RCF-OFFLINE-HTTP-IPC`, `RCF-ONEROSTER`, `RCF-RESOURCE-REDIRECT-GAP`,
`RCF-WEB-LIFECYCLE-GAPS`, and `RCF-XAPI-BINDING-OUTCOME-GAPS`.

They require feature-addressed acceptance work and cannot close until a unique
normative behavior and executable acceptance contract exist.

## Artifact and consumer inventory

| Family | Baseline format and authority |
|---|---|
| Suite JSON/text/JUnit | unversioned Suite report; meanings duplicated across report and CLI |
| Evidence manifest | `1.0.0`, built in `respect_compat.handoff` |
| Kit task packet | `1.0.0`, generic CanApp-owner/actionable-state projection |
| Kit work plan and narrow verifier | `1.0.0`, non-certifying |
| Kit ledger | append-only hash chain with repair-specific transitions |
| Promotion packet | absent |
| Platform-gap packet | absent |
| Upgrade Dossier, lifecycle, ledger, verifier, CLI | absent |
| Legacy verification | current artifacts verified against the currently installed Matrix; no frozen routing-family adapter |

Current installed-wheel entry points are `respect-compat`,
`respect-ification`, `respect-matrix-validate`,
`respect-standards-bootstrap`, and `respect-runtime-driver-build`.

## Phase 0 conclusion

The pre-existing baseline is green. The routing and Dossier work can proceed
without opening the RESPECT authorization gate. The baseline contains no
qualifying platform-gap evidence and therefore authorizes no actual Upgrade
Dossier.
