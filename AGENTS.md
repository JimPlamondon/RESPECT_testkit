# RESPECT TestKit Agent Instructions

These instructions govern coding agents and review agents working in this repository.

## Repository workflow

- Read `README.md`, `CONTRIBUTING.md`, and `docs/AI_OPERATOR.md` before changing code.
- Work only on a task branch in an isolated Git worktree. Never commit or push directly to `main`, force-push, bypass hooks, or weaken a gate to make a change pass.
- Preserve every file. Do not delete files. Move any file that would otherwise be removed into `To_Be_Deleted/`, preserving its repository-relative path, and document why it is no longer active.
- Use Developer Certificate of Origin sign-off for every authored commit.
- Keep each change focused and record red/green evidence: a failing reproduction or changed-behavior receipt before the fix, followed by the narrow verifier and relevant broad gates after the fix.
- Treat historical audit findings as leads that must be reproduced against the current commit before repair.

## Product authority

- The RESPECT Compatible Test Suite is the sole compatibility-verdict authority.
- The RESPECT-ification Kit consumes immutable Test Suite artifacts and remains non-certifying.
- The canonical Compatibility Matrix is the sole requirements authority. Do not change its obligations, applicability, verdict semantics, or semantic hash merely to make tests pass.
- Narrow verification is always non-certifying. Only a complete applicable Test Suite run can establish compatibility.
- Preserve evidence binding, target identity, attribution, privacy boundaries, owner-local private Prep, and the distinction among CanApp, TestKit, RESPECT Platform, publisher, and Spix Foundation responsibility.
- Never manufacture owner facts, credentials, legal consent, signing identity, physical-device evidence, RESPECT Platform evidence, or certification authority.

## Verification expectations

- Start with the smallest reliable verifier for the changed behavior, then run the full Python test suite and the Compatibility Matrix validator with self-tests and readiness required.
- Run the migration-manifest validator for every campaign change.
- For packaging, resources, schemas, entry points, or command-line changes, build and inspect the distribution and run installed-wheel acceptance outside the checkout.
- Run licensing and privacy gates when their surfaces are affected.
- Distinguish local verification from GitHub Actions Continuous Integration status.
- Stop and report honestly when a required real device, deployed origin, credential, authority, or human fact is unavailable.

## Code Review Rules

- The first review pass is read-only. The reviewer must not edit the implementation it is judging.
- Review the original requirement, governing contracts, committed diff, tests, and generated artifacts before reading the implementer's rationale.
- Try to falsify the change. Look for false-positive compatibility verdicts, false attribution, weakened Matrix or evidence semantics, privacy leakage, unsafe input handling, replay or substitution, command injection, path escape, incorrect exit behavior, package-resource failures, documentation drift, and missing hostile or isolated-negative tests.
- Do not accept a test that merely repeats the implementation's logic as an independent oracle.
- Every actionable finding must identify the affected file and behavior, severity, failure mechanism, and a concrete reproduction or smallest test that would expose it.
- Do not report formatting or stylistic preferences as bugs. Leave mechanical style checks to automation.
- The implementer, not the reviewer, repairs accepted findings. The reviewer then rereads the resulting commit and verifies that the repair did not introduce adjacent regressions.
- A clean review must say `no actionable findings` and list remaining uncertainty, unexecuted environment-dependent checks, and manual acceptance gates.
