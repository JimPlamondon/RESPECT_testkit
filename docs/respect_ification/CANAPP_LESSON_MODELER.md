# CanApp Lesson Modeler

The CanApp Lesson Modeler turns an owner-confirmed lesson inventory and an
evidence-backed interaction model into ordinary TestKit runtime scenarios. It
supports three lessons, arbitrary lesson lists, courses, interaction families,
or the complete inventory without changing Test Suite authority.

The deterministic Modeler does not infer lesson meaning, call a hosted
artificial-intelligence service, execute Candidate App (`CanApp`) source, or
modify the TestKit. When source/runtime interpretation is required, `analyze`
writes a private, source-bound prompt and `Human_ToDo.md` for an
owner-authorized AI or human.

## Concepts

- **Inventory:** the canonical owner-confirmed lesson list, with optional
  course, unit, locale, version, safe source reference, and namespaced metadata.
- **Interaction family:** a shared technical lifecycle and bounded scenario
  template used by one or more lessons.
- **Classification:** exactly one evidence-backed family, `unclassified`, or
  an owner exclusion for each modeled lesson.
- **Binding:** typed owner-local values substituted into a family template.
- **Selection:** an exact content-bound request by lesson, course, family, all,
  and optional exclusions.
- **Run plan:** the selected lessons and either one validated ordinary scenario
  or a blocking reason for each.
- **Coverage:** separate counts for inventory, modeling, selection,
  compilation, execution, and outcomes.
- **Capability gap:** a generic missing TestKit mechanism. It contains no
  lesson identifier, answer, selector, or geometry and does not change the
  TestKit.

Sampling representatives can validate an interaction family. Sampling never
proves that the unexecuted inventory passed.

## Owner-local artifacts

All artifacts use format `1.0.0`, carry a canonical semantic hash, and bind
their exact inputs:

- `canapp-lesson-inventory.json`
- `canapp-lesson-model.json`
- `canapp-lesson-selection.json`
- `canapp-lesson-modeling-packet.json`
- `canapp-lesson-run-plan.json`
- `canapp-lesson-capability-gaps.json`
- `canapp-lesson-coverage.json`
- `respect-execution-log.jsonl`

Keep these artifacts in the CanApp owner's private workspace. Do not put
lesson identifiers, answers, selectors, stroke paths, source facts, or learner
data in the TestKit repository.

## Analyze

Given an already confirmed inventory, create the private modeling packet and
human handback:

```sh
respect-ification lesson-model analyze \
  --source-root /owner/private/canapp \
  --inventory /owner/private/model/canapp-lesson-inventory.json \
  --output-dir /owner/private/model/analyze
```

The packet records relative file names, sizes, and hashes for bounded files. It
does not copy source contents. The generated prompt asks the owner-authorized
modeler to identify technical families, evidence, typed parameters, bindings,
and ambiguity. Unknown lessons remain unclassified.

## Validate

```sh
respect-ification lesson-model validate \
  --artifact /owner/private/model/canapp-lesson-inventory.json \
  --artifact /owner/private/model/canapp-lesson-model.json \
  --artifact /owner/private/model/canapp-lesson-selection.json \
  --output-dir /owner/private/model/validation
```

Schema validity is necessary but insufficient. Validation also checks semantic
hashes, bindings, duplicate identities, path safety, classifications, and
artifact lineage.

## Select and compile

A selection can combine exact lesson, course, and family lists. `all: true`
selects the complete inventory. Explicit exclusions are applied last.
Duplicate, unknown, or accidentally empty selections fail.

```sh
respect-ification lesson-model compile \
  --inventory /owner/private/model/canapp-lesson-inventory.json \
  --model /owner/private/model/canapp-lesson-model.json \
  --selection /owner/private/model/canapp-lesson-selection.json \
  --testkit-commit 0123456789abcdef0123456789abcdef01234567 \
  --target-id synthetic-target \
  --target-digest aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --profile PROFILE-NATIVE_ANDROID \
  --output-dir /owner/private/model/compiled
```

By default, compilation compares families with the action vocabulary in the
running TestKit. `--available-capability` may restrict that set for a diagnostic
check; it cannot name an unknown action.

Templates may use only an object containing one `$binding` member:

```json
{"$binding": "activity_id"}
```

The family declares the binding's JSON type. Substitution does not evaluate
expressions or code. The compiled result must pass the existing native runtime
scenario validator.

Unclassified lessons, missing bindings, or missing capabilities remain in the
run plan with `status: "blocked"`. Compilation returns exit code 2 when any
selected lesson is blocked.

## Execute

Execution currently uses the existing native Android runtime driver. The run
plan supplies each generated scenario; do not also pass `--runtime-scenario`.

```sh
respect-ification lesson-model execute \
  --run-plan /owner/private/model/compiled/canapp-lesson-run-plan.json \
  --apk-only \
  --apk /owner/private/build/canapp.apk \
  --device-id emulator-5554 \
  --runtime-driver-apk /owner/private/runtime/driver.apk \
  --runtime-gesture-apk /owner/private/runtime/gesture.apk \
  --runtime-driver-receipt /owner/private/runtime/driver.receipt.json \
  --output-dir /owner/private/model/run
```

Each compiled lesson receives a collision-safe child directory and an ordinary
complete selected-profile TestKit run. Each child's `respect-report.json`
remains authoritative for that exact run. The parent
`canapp-lesson-batch-index.json` is a non-authoritative routing index.

The batch exits zero only when every selected child exits zero and has outcome
`passed`. Otherwise it exits 2. An uncompiled lesson receives a
`modeler-blocked.json` receipt, not a counterfeit TestKit report.

Use `--resume` only after an interruption. Resume verifies the run-plan hash,
target/TestKit bindings, scenario hashes, child count, child report paths, and
child report bytes. Any mismatch rejects resume.

## Coverage

```sh
respect-ification lesson-model status \
  --inventory /owner/private/model/canapp-lesson-inventory.json \
  --model /owner/private/model/canapp-lesson-model.json \
  --selection /owner/private/model/canapp-lesson-selection.json \
  --run-plan /owner/private/model/compiled/canapp-lesson-run-plan.json \
  --batch-index /owner/private/model/run/canapp-lesson-batch-index.json \
  --output-dir /owner/private/model/status
```

Omit `--batch-index` to report modeling and compilation coverage before
execution. Coverage distinguishes `inventoried`, `classified`, `unclassified`,
`excluded`, `selected`, `compiled`, `executed`, `passed`, `failed`, `blocked`,
and `incomplete`.

`full_inventory_executed` becomes true only when the complete inventory was
selected and every inventory item has an indexed execution outcome.

## Privacy and authority

Every operation writes the mandatory hash-chained execution log. Logs contain
counts, artifact hashes, scenario hashes, and hashed lesson references—not
answers, selectors, attributes, paths, coordinates, credentials, learner data,
or raw lesson content.

Modeler output, generated prompts, compilation, emulator runs, and the parent
batch index are not certification. Only each complete applicable Test Suite
run can produce its ordinary report, and external provisions remain external.
