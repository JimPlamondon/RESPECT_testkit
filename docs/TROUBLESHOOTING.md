# Troubleshooting

Start with `respect-report.txt`, then inspect the same row in
`respect-report.json`. Preserve its six routing dimensions before deciding
what to change.

## Decision guide

| Symptom | Meaning | Action |
|---|---|---|
| `canapp_implementation_fail` | Target-attributable product defect | Generate and execute Kit repair work |
| `blocked`, `incomplete`, or `deferred` | Behavior was not established | Supply the named dependency; do not blame the CanApp |
| `testkit_capability_gap` | No adequate suite observer | Create TestKit engineering work |
| `harness_error` or exit 3 | Suite-owned actor malfunction or report-integrity failure | Preserve outputs and diagnose the actor |
| `respect_platform_gap` | Qualifying real RESPECT evidence failed | Route to the RESPECT Platform team |
| `Provisional (...)` | Some behavior passed but final evidence or authority is missing | Follow every provision's clearance and rerun scope |

## Installation and standards

### Command not found

Activate the environment used to install the package and confirm its `bin`
directory is on `PATH`. Prefer `python -m pip install -e '.[test]'` in a
virtual environment.

### Standards cache missing or wrong revision

Run:

```sh
respect-standards-bootstrap
respect-standards-bootstrap --check
```

Use the same `RESPECT_STANDARDS_CACHE` or `--cache` value for both. A cache
with another revision must not be treated as equivalent.

## Invocation and binding

### Exit 64

The CLI rejected arguments or an input artifact. Read the final error line.
Common causes include:

- missing `--apk` with `--apk-only`;
- incomplete runtime-driver or RESPECT-platform argument groups;
- runtime execution without `--device-id`;
- `--run-seed` in certification mode;
- challenge shorter than 16 characters;
- mixed, stale, or tampered report/evidence/task artifacts;
- unsafe absolute or escaping paths inside owner-authored artifacts.

### Work-plan or semantic-hash mismatch

Do not edit bound JSON manually. Regenerate the work plan from one unchanged
Test Suite handoff. If the canonical Matrix or target changed, run the Test
Suite again.

### Prompt and `Human_ToDo.md` differ

Compare the prompt's SHA-256 with the value in `Human_ToDo.md`. Do not run a
different prompt under the old ToDo. Regenerate with `repair-plan`.

## HTTPS publication

### Local certificate rejected

Pass the local CA certificate with `--ca-cert`; do not disable TLS validation.
The certificate still must match the hostname.

### Production pack verifies locally but not for certification

Production verification requires `publication-verify --deployed-origin`.
The deployed resources must match the pack byte-for-byte and provide declared
media types, lengths, validators, and successful conditional responses.

### Immutable artifact URL failure

The URL path must contain the exact submitted artifact's SHA-256 digest. It
must return identical bytes with immutable cache semantics.

### Publication authorization remains pending

Rerun `publication-authorization` with the same state file. Pending requests
are checked idempotently. Do not create another request. Replacing a declined,
voided, or expired request requires explicit
`--replace-terminal-request`.

## Android runtime

### Runtime-driver arguments rejected

Supply `--runtime-driver-apk`, `--runtime-driver-receipt`, and
`--runtime-scenario` together, plus the submitted `--apk` and `--device-id`.
The receipt must bind the exact suite-owned driver source and APK.

### Device or emulator evidence blocked

Confirm `adb devices -l`, select the device explicitly, and inspect the
reported device probe. Emulator evidence can establish behavior but retains
the physical-device provision when that evidence is policy-required.

### RESPECT Platform scenario rejected

Supply the platform APK, build receipt, scenario, and device together. The
receipt must bind a clean source revision. Selected rows, devices, packages,
target digest, challenge, and APK digest must match the active run.

## When to rerun

Use the provision's `rerun_scope`:

- `affected_rows` means the clearance evidence can focus on those rows;
- `full_selected_profile` means the complete profile must run again.

Final certification always requires a complete applicable certification run,
even after narrow verification or affected-row diagnostics.

## Reporting a TestKit problem

Preserve the report, evidence manifest, task packet, mandatory execution log,
JUnit output, exact TestKit commit/version, operating environment, and
actor/build receipts. The execution log already redacts recognized secret
arguments, but review every artifact before publication. Do not publish private
CanApp source, credentials, hidden certification inputs, or exploit material.
