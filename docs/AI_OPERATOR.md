# Instructions to code-capable AIs

This is the normative operating entry point for an AI asked to install the
RESPECT TestKit and apply it to a Candidate App (`CanApp`).

## Objective

Safely progress the supplied CanApp as far toward RESPECT compatibility as the
available code, harness, authority, infrastructure, and evidence permit. Keep
the Human in the Loop informed through `Human_ToDo.md`. Finish with a complete
applicable Test Suite run whenever the required environment is available.

## Non-negotiable boundaries

- Treat the Test Suite, canonical Compatibility Matrix, result routing,
  evidence, and verdict reducer as immutable certification authority. Do not
  alter them to make the CanApp pass.
- Never manufacture owner facts, lesson meaning, credentials, legal consent,
  publication authority, signing identity, physical-device evidence, or
  RESPECT Platform evidence.
- Never treat a fixture, generated prompt, source inspection, narrow verifier,
  local HTTPS publication, substitute, or emulator as final certification.
- Do not credit suite companion behavior or owner-authored pass flags to the
  CanApp.
- Keep generated repair adapters and source-analysis data out of the production
  CanApp.
- Preserve proprietary CanApp source and private Prep inside the owner's
  environment. Do not copy secrets or private certification material into
  reports or this repository.
- Stop at a missing human fact or authority rather than substituting a
  plausible value.

## 1. Establish the workspace

Locate:

- the TestKit checkout or wheel;
- the CanApp source root, if supplied;
- the exact APK or web target to assess;
- the intended profile;
- authorized Android devices, emulators, HTTPS origins, and credentials.

If the profile is not explicit, infer only when the target form makes it
unambiguous:

- web CanApp: `PROFILE-WEB`;
- native Android CanApp: `PROFILE-NATIVE_ANDROID`;
- TestKit self-assurance: `PROFILE-SUITE_QUALITY`;
- future claims: `PROFILE-CLAIMED_FUTURE`.

Ask the Human when selecting the wrong profile could change the work.

## 2. Install and verify the TestKit

From a source checkout, prefer an isolated environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

The declared minimum Python version is 3.9. Do not claim broader operating
system or device support that has not been exercised.

Provision the source-locked OPDS and Readium standards cache:

```sh
respect-standards-bootstrap
respect-standards-bootstrap --check
```

`--check` is read-only and network-free. `RESPECT_STANDARDS_CACHE` or
`--cache` selects another cache root.

Confirm the commands resolve:

```sh
respect-compat --help
respect-ification --help
respect-matrix-validate --help
```

For TestKit development, run `pytest -q` before relying on a modified checkout.

## 3. Run the first assessment

Use a fresh output directory. Never seed certification mode.

For a raw native Android CanApp without a discovery surface:

```sh
respect-ification full-test \
  --apk-only \
  --apk /absolute/path/to/canapp.apk \
  --profile PROFILE-NATIVE_ANDROID \
  --output-dir /absolute/path/to/run-01
```

For a published descriptor:

```sh
respect-ification full-test \
  --manifest-url https://owner.example/canapp/manifest.json \
  --profile PROFILE-WEB \
  --output-dir /absolute/path/to/run-01
```

For an owner-controlled server base:

```sh
respect-ification full-test \
  --server-base-url https://owner.example/canapp/ \
  --profile PROFILE-WEB \
  --output-dir /absolute/path/to/run-01
```

Use `--ca-cert` only for an explicitly provisioned local certification
authority. Hostname and certificate validation remain required.

For native Android lessons that require tracing, drawing, dragging, or
handwriting, use a format `1.1.0` owner-local runtime scenario with bounded
`stroke` actions. Keep lesson identifiers, accessibility selectors, and path
geometry in the CanApp workspace; do not add them to TestKit. Build the
suite-owned xAPI and gesture APKs together, pass the gesture APK with
`--runtime-gesture-apk`, and retain the build receipt. A gesture receipt proves
injection of the declared path, not lesson recognition or completion. See
`docs/respect_compat/NATIVE_ANDROID_RUNTIME_DRIVER.md`.

Read:

- `respect-report.txt` for the human summary;
- `respect-report.json` for the authoritative structured run;
- `respect-evidence-manifest.json` for sanitized evidence;
- `respect-ification-task-packet.json` for CanApp repair work;
- `respect-execution-log.jsonl` for the chronological, hash-chained execution
  record, including every selected Matrix row;
- `junit.xml` for automation.

Interpret exit codes using [ARTIFACTS_AND_REPORTS.md](ARTIFACTS_AND_REPORTS.md).
An exit code of 2 is a non-final outcome, not a process crash.
The execution log is mandatory and cannot be disabled. Preserve it with every
run, including unsuccessful and non-final runs.

### Model a lesson inventory

When a CanApp has many lessons or multiple lesson engines, use the CanApp
Lesson Modeler before writing one-off runtime scenarios. The owner supplies a
confirmed inventory and an evidence-backed owner-local family model. The
Modeler selects three lessons, arbitrary lessons, courses, families, or the
complete inventory and compiles ordinary TestKit scenarios.

Keep identifiers, answers, selectors, gesture geometry, and source facts in
the owner workspace. An unclassified selected lesson fails closed. A generic
capability gap is reported separately and never changes the TestKit
automatically. See
`docs/respect_ification/CANAPP_LESSON_MODELER.md`.

## 4. Route the outcome before changing anything

Use each result's `requirement_owner`, `control_owner`, `responsible_party`,
`verification_mode`, `observed_result`, and `workflow_disposition`.

- `canapp_implementation_fail` authorizes owner-local Kit repair.
- `code_compatible_through_substitute` requires promotion against the real
  dependency, not more CanApp blame.
- `unmeasured_external_dependency` requires provisioning or observation.
- `testkit_capability_gap` belongs to the TestKit team.
- `harness_error` is an attributable TestKit actor incident.
- `respect_platform_gap` is a neutral real-platform observation and does not
  authorize CanApp repair.
- `specification_blocked` requires a specification decision.

Do not infer a CanApp defect from blocked or absent evidence.

## 5. Generate owner-local repair work

The Test Suite output already contains the immutable handoff. Optionally
prepare private source hints:

```sh
respect-ification prepare \
  --source-root /absolute/path/to/source-collection \
  --target-digest TARGET_SHA256 \
  --profile PROFILE-NATIVE_ANDROID \
  --public-output /absolute/path/to/work/public-prep.json \
  --private-output /absolute/path/to/work/private-prep.json
```

Copy `target_digest` exactly from `respect-report.json`.

Create the bound work plan:

```sh
respect-ification plan \
  --report /absolute/path/to/run-01/respect-report.json \
  --evidence-manifest /absolute/path/to/run-01/respect-evidence-manifest.json \
  --task-packet /absolute/path/to/run-01/respect-ification-task-packet.json \
  --private-prep /absolute/path/to/work/private-prep.json \
  --output /absolute/path/to/work/work-plan.json
```

Omit `--private-prep` when it was not generated.

Generate the source-derived prompt and Human handback:

```sh
respect-ification repair-plan \
  --work-plan /absolute/path/to/work/work-plan.json \
  --source-root /absolute/path/to/source-collection \
  --canapp-root relative/path/to/canapp \
  --testkit-commit TESTKIT_GIT_COMMIT \
  --adapter-output /absolute/path/to/work/repair-adapter.json \
  --prompt-output /absolute/path/to/work/repair-prompt.md \
  --human-todo-output /absolute/path/to/work/Human_ToDo.md
```

`--canapp-root` is relative to `--source-root`; omit it when they are the same.

## 6. Execute the generated prompt

Read both `repair-prompt.md` and `Human_ToDo.md`. Verify that the ToDo's prompt
path and SHA-256 match before starting.

The generated prompt may change normal CanApp production code, build logic,
tests, and genuinely external publication harnesses. Follow its truth
contracts and forbidden-substitute rules. Do not generalize proprietary lesson
semantics into the TestKit.

When the prompt finishes or blocks, update `Human_ToDo.md` in place as its
handback contract requires:

- mark delegated work completed or blocked;
- summarize actual changes;
- record verification and results;
- leave only human-owned actions;
- state the required full Test Suite rerun;
- never state that prompt completion is certification.

## 7. Track and narrowly verify repair tasks

Inspect ledger state:

```sh
respect-ification status \
  --work-plan /absolute/path/to/work/work-plan.json \
  --ledger /absolute/path/to/work/repair-ledger.jsonl
```

Record only work actually performed. Valid transitions are enforced by the
ledger implementation. Use `record --help` and never invent a verifier receipt.

Run the suite-owned narrow verifier for a task:

```sh
respect-ification verify \
  --work-plan /absolute/path/to/work/work-plan.json \
  --task-id repair:ROW-ID \
  --manifest-url https://owner.example/canapp/manifest.json \
  --output /absolute/path/to/work/ROW-ID-verifier.json
```

The target options match `full-test`. A narrow result is always
`narrow_non_certifying`.

## 8. Build and verify publication artifacts when required

Follow [CERTIFICATION_WORKFLOW.md](CERTIFICATION_WORKFLOW.md) for lesson
inventory, publication manifest, provisional or production pack, deployed
verification, publication authorization, Android runtime evidence, and final
rerun. Source-derived candidates are evidence, not a declared lesson inventory.

Production facts must come from the owner. Production packs require the exact
submitted APK, a release signer, a stable owner-controlled HTTPS origin, and
deployed-origin verification.

## 9. Finish with the complete profile

After all available repair and provisioning:

1. Rerun `respect-ification full-test` against the repaired exact target.
2. Preserve the output directory unchanged.
3. Report the exact verdict, not a paraphrased success.
4. List every remaining provision with responsible party and clearance action.
5. Update `Human_ToDo.md` with only unresolved human actions.
6. If the environment cannot execute the complete profile, state that
   certification remains unmeasured or provisional.

## Required final response to the Human

Include:

- TestKit version or Git commit;
- CanApp target identifier and digest;
- selected profile;
- exact verdict and exit code;
- report and `Human_ToDo.md` paths;
- files or systems changed;
- verification performed;
- remaining provisions and owners;
- exact next action or rerun.
