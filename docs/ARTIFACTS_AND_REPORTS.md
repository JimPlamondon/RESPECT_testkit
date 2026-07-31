# Artifacts and reports

## Test Suite output directory

A Matrix-driven run writes:

```text
OUTPUT/
├── respect-report.json
├── respect-report.txt
├── respect-evidence-manifest.json
├── respect-ification-task-packet.json
└── junit.xml
```

- `respect-report.json` is the authoritative structured run.
- `respect-report.txt` is the human-readable projection.
- `respect-evidence-manifest.json` is the exact sanitized evidence projection.
- `respect-ification-task-packet.json` contains only authorized CanApp repair
  tasks.
- `junit.xml` represents a CanApp defect as a failure, a TestKit actor
  malfunction as an error, and other non-final dispositions as skipped.

The JSON report, evidence manifest, and task packet are mutually bound by core
hashes and one `handoff_id`. Do not mix artifacts from different runs or format
generations.

## Result dimensions

Every Matrix row preserves:

- `requirement_owner`;
- `control_owner`;
- `responsible_party`;
- `verification_mode`;
- `observed_result`;
- `workflow_disposition`;
- authorized follow-on `artifacts`;
- whether the dimension is policy-required and final-affirmative.

The row's behavioral state (`pass`, `fail`, `blocked`, and so on) and its
attributed workflow result answer different questions. Consumers must not
derive their own routing from the behavioral state alone.

## Verdicts

- `Certified`: every policy-required dimension is final and affirmative.
- `Provisional (...)`: established behavior is retained, but named evidence or
  authority must be promoted.
- `Not certified`: at least one required dimension is non-final.
- `Incomplete`: the required evaluation set was not completed.
- `Non-certification mode`: the run was intentionally diagnostic or replayed.

A provision records a stable code, explanation, affected rows, evidence
environment, clearance action, rerun scope, and responsible party. Current
families include TestKit capability, fixture evidence, emulated Android,
local HTTPS publication, publication authorization, immutable exact-build
hosting, and certification trust-anchor conditions.

## Exit codes

### `respect-compat`

| Code | Meaning |
|---:|---|
| 0 | Certified in certification mode, or complete affirmative diagnostic run |
| 1 | At least one attributable CanApp-owned failure |
| 2 | Valid but non-final result: provisional, blocked, incomplete, or deferred |
| 3 | Independent report verification failed or a harness error occurred |
| 64 | Invalid invocation or rejected input |

### `respect-ification`

Most generation and record commands return 0 on success. `publication-verify`,
`publication-authorization`, and narrow `verify` return 2 for a valid but
non-final or failing result. Invocation and validation errors return 64.
`full-test` preserves the Test Suite's exit code and verdict.

## RESPECT-ification artifacts

The repair flow may create:

- public and private Prep packets;
- a bound local work plan;
- a Kit-time repair adapter;
- a source-derived implementation prompt;
- `Human_ToDo.md`;
- an append-only repair ledger;
- narrow, non-certifying verifier receipts;
- publication manifest, pack, deployment contract, and verification receipt.

`Human_ToDo.md` binds the exact prompt path and SHA-256. If they differ,
regenerate the repair plan. The prompt executor updates the file on success or
blockage, leaving only human-owned actions.

## Independent interpretation

Use the report's exact verdict and provisions. Do not infer certification from
process exit alone, the absence of Kit tasks, a narrow pass, or a completed
`Human_ToDo.md`.
