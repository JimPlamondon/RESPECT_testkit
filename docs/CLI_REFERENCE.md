# Command-line reference

The CLI parser is the syntax authority. Run `COMMAND --help` and
`respect-ification SUBCOMMAND --help` for the installed version. This page
explains intent, groups, and exit behavior.

Every `respect-compat` run and every `respect-ification` subcommand writes a
mandatory hash-chained JSON Lines execution log. Full runs write
`respect-execution-log.jsonl` inside `--output-dir`; other commands place the
log beside their primary output. See
[ARTIFACTS_AND_REPORTS.md](ARTIFACTS_AND_REPORTS.md).

## Test Suite commands

### `respect-compat`

Runs the Matrix-driven Test Suite against exactly one target:

```text
respect-compat TARGET --profile PROFILE --mode MODE --output-dir DIR [OPTIONS]
```

Target is exactly one of `--manifest-url`, `--server-base-url`,
`--fixture-dir`, or `--apk-only`. `--apk-only` requires `--apk`.

Important groups:

- Native runtime: `--runtime-driver-apk`, `--runtime-driver-receipt`, and
  `--runtime-scenario` must appear together with `--apk` and `--device-id`.
- RESPECT Platform: `--respect-platform-apk`,
  `--respect-platform-build-receipt`, and
  `--respect-platform-scenario` must appear together with `--device-id`.
- Publication: `--publication-artifact`, `--immutable-artifact-url`, and
  `--publication-authorization-token` bind exact-build publication evidence.
- Trust: `--spix-public-key` exercises rejection of submission-supplied trust;
  it cannot establish Foundation authority. `--certification-key-state-dir`
  selects the persistent testing-key state.
- Reproducibility: `--run-seed` is allowed only in `test` or `replay`.
  `--challenge` must contain at least 16 characters.

### `respect-standards-bootstrap`

Without `--check`, clones/fetches and checks out the source-locked OPDS and
Readium revisions. With `--check`, verifies the cache without writes or
network. `--cache` overrides `RESPECT_STANDARDS_CACHE` and the default user
cache.

### Other installed Test Suite commands

- `respect-matrix-validate`: validate the canonical Matrix.
- `respect-runtime-driver-build`: build and receipt-bind the suite-owned
  Android companion.
- `respect-platform-receipt`: bind a RESPECT APK to a clean source revision.
- `respect-platform-adb-provider`: execute bounded platform observation
  workflows.
- `respect-school-harness`: orchestrate the documented school harness.

Use their installed `--help`; specialized runtime operation is documented
under `docs/respect_compat/`.

## RESPECT-ification commands

### `prepare`

Creates public Prep and optional owner-local private Prep from a source root,
target digest, and profile.

### `plan`

Validates one report/evidence/task handoff and emits a bound local work plan.
Optional private Prep contributes source hints only.

### `repair-plan`

Analyzes the supplied source, selects complete Matrix truth contracts, and
writes the repair adapter, implementation prompt, and synchronized
`Human_ToDo.md`.

### `truth-audit`

Emits the content-bound disposition of every canonical Matrix row.

### `publication-manifest`

Combines a repair adapter, confirmed source-bound lesson inventory, and
owner-supplied identity facts into a normalized publication manifest.

### `publication-pack`

Builds a provisional or production publication. Exactly one of
`--signing-fingerprint` and `--apk` is required. Production requires stronger
origin, signer, APK, and deployment bindings.

### `publication-verify`

Verifies pack structure and optionally the deployed HTTPS origin. Production
verification requires `--deployed-origin`. `--ca-cert` requires a deployed
origin.

### `publication-serve`

Serves a generated pack, defaulting to `127.0.0.1:8765`. `--certfile` and
`--keyfile` enable TLS.

### `publication-authorization`

Idempotently ensures the publisher agreement and requests an exact-build
authorization token. State and token output are owner-private.

### `status` and `record`

Read or append to the hash-chained repair ledger. `record` requires work plan,
ledger, task, state, and note. Local verification also requires a safe
verifier-result reference.

### `verify`

Runs a single suite-owned narrow verifier for a work-plan task against one
target. The receipt is non-certifying.

### `full-test`

Runs the complete Test Suite in certification mode and preserves its exit code
and verdict. It supports the same target and runtime evidence options as
`respect-compat`.

## Exit codes

See [ARTIFACTS_AND_REPORTS.md](ARTIFACTS_AND_REPORTS.md). In particular, 2
usually means a valid but non-final outcome, while 64 means rejected input or
invocation.
