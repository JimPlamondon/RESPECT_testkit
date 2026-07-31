# Public reports

Test Suite report formats are public. Generated reports are run output and are
not tracked or packaged. See [artifacts and reports](ARTIFACTS_AND_REPORTS.md)
for the output tree, exit codes, and interpretation rules.

## Row outcomes and approval

Each Matrix row reports observed behavior as `pass`, `fail`,
`not_applicable`, `incomplete`, `deferred`, `harness_error`, or `blocked`.
Typed attribution separately records ownership, verification mode, observed
result, workflow disposition, and authorized follow-on artifacts.

The overall verdict is `Certified`, `Provisional (...)`, `Not certified`,
`Incomplete`, or `Non-certification mode`. A provision contains a stable code,
label, explanation, affected Matrix rows, evidence-environment facts,
clearance action, rerun scope, and responsible party.

Provision families cover:

- unavailable TestKit observation;
- suite-fixture evidence;
- attributable emulator evidence requiring physical-device confirmation;
- local rather than stable owner-controlled HTTPS publication;
- missing or testing-only Spix certification trust;
- missing exact-build publication authorization;
- missing immutable certified-build acquisition.

Multiple provisions remain visible together. Independent report verification
recomputes them from bound evidence and rejects removed, added, or altered
provisions.

Clearing a provision requires its stated follow-up evidence, not changing an
already truthful passing row. A passing substitute result can remain passing
while final approval waits for promotion.
