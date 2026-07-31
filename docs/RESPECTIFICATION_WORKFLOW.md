# RESPECT-ification workflow

The Kit turns immutable, attributable CanApp failures into owner-local repair
work. It is not a second compatibility oracle.

## Inputs

Use the three files from one Test Suite output directory:

- `respect-report.json`;
- `respect-evidence-manifest.json`;
- `respect-ification-task-packet.json`.

They must have format version `2.0.0` and the same artifact-set bindings.
Legacy routing artifacts are read-only and cannot generate new work.

## Optional private Prep

`prepare` inventories owner-local source and may add relative source hints.
Private Prep never changes requirements, outcomes, evidence, or verdicts.

```sh
respect-ification prepare \
  --source-root /absolute/path/to/source \
  --target-digest COPY_FROM_REPORT \
  --profile PROFILE-WEB \
  --public-output /absolute/path/to/work/public-prep.json \
  --private-output /absolute/path/to/work/private-prep.json
```

Do not publish private Prep.

## Bound work plan

```sh
respect-ification plan \
  --report /absolute/path/to/run/respect-report.json \
  --evidence-manifest /absolute/path/to/run/respect-evidence-manifest.json \
  --task-packet /absolute/path/to/run/respect-ification-task-packet.json \
  --private-prep /absolute/path/to/work/private-prep.json \
  --output /absolute/path/to/work/work-plan.json
```

The plan preserves every normative task unchanged. Its source hints are
nonnormative.

## Prompt and Human handback

```sh
respect-ification repair-plan \
  --work-plan /absolute/path/to/work/work-plan.json \
  --source-root /absolute/path/to/source \
  --testkit-commit TESTKIT_GIT_COMMIT \
  --adapter-output /absolute/path/to/work/repair-adapter.json \
  --prompt-output /absolute/path/to/work/repair-prompt.md
```

By default, this writes `Human_ToDo.md` beside the prompt.
`--human-todo-output` selects another path.

The ToDo binds the exact prompt by path and SHA-256. The initial human action
may be only to run that prompt and reopen the ToDo afterward. The prompt's
handback contract requires its executor to update the file when successful or
blocked.

## Repair requirements

The prompt directs durable changes into normal CanApp code, its build, its
tests, and genuinely external services. It includes Matrix expectations,
positive and negative cases, implementation targets, source seams, evidence
class, and forbidden substitutes.

The executor must not:

- retain the generated adapter as production runtime behavior;
- introduce TestKit-recognizing or debug-only success paths;
- simulate CanApp behavior in a provisional service;
- invent lesson identity or proprietary meaning;
- edit Test Suite results, requirements, or trust metadata.

## Ledger

The append-only ledger checks its hash chain and legal state transitions.
Typical task progression is diagnosis, implementation, verification, and
local verification; use `status` to inspect the authoritative current state
and `record --help` for the required transition input.

```sh
respect-ification status \
  --work-plan /absolute/path/to/work/work-plan.json \
  --ledger /absolute/path/to/work/repair-ledger.jsonl
```

A `locally_verified` transition requires a safe relative reference to a
matching suite-owned verifier receipt. Ledger notes cannot record a
certification verdict.

## Narrow verification

```sh
respect-ification verify \
  --work-plan /absolute/path/to/work/work-plan.json \
  --task-id repair:ROW-ID \
  --server-base-url https://owner.example/canapp/ \
  --output /absolute/path/to/work/ROW-ID-verifier.json
```

The target arguments are the same as the Test Suite. The verifier binds the
row, work plan, target lineage, challenge, and observation, but its result is
always non-certifying.

## Completion

Repair is complete only when:

1. prompt-covered work has been applied durably;
2. the prompt has updated `Human_ToDo.md`;
3. required narrow verifiers have passed;
4. human-owned prerequisites have been completed or remain explicitly listed;
5. the complete selected Test Suite profile has been rerun against the exact
   repaired target.

The full run's exact verdict supersedes no prior evidence; it establishes the
current target's status.

## CanApp Lesson Modeler

Use `respect-ification lesson-model` when the CanApp's lesson inventory needs
repeatable partial, course, family, or complete-inventory runtime coverage. The
Modeler keeps lesson facts owner-local, compiles through the existing scenario
validator, and invokes one ordinary complete selected-profile run per
compilable selected lesson.

Per-lesson reports remain authoritative. Coverage and the batch index are
non-authoritative. Sampling a family does not equal executing every lesson.
See [CANAPP_LESSON_MODELER.md](respect_ification/CANAPP_LESSON_MODELER.md).
