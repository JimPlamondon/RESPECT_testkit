# Public Reports

Test Suite report formats are public. Generated reports are run output and are not tracked or packaged.

## Row outcomes and approval

Each Matrix row reports the behavior actually observed as `pass`, `fail`, `not_applicable`, `incomplete`, `deferred`, `harness_error`, or `blocked`. The approval reducer does not rewrite a passing behavioral result merely because its evidence came from a provisional environment.

The overall verdict separately reports `Certified`, `Provisional (...)`, `Not certified`, `Incomplete`, or `Non-certification mode`. A Provisional verdict contains a structured `provisions` array. Every provision has a stable code, short label, explanation, affected Matrix rows, evidence-environment facts, clearance action, rerun scope, and responsible party.

Current automatically detected provisions are `EMULATED_ANDROID_RUNTIME` (the applicable Android behavior passed on an attributable emulator), `LOCAL_HTTPS_PUBLICATION` (publication behavior passed at a local Hypertext Transfer Protocol Secure origin), and `SUITE_FIXTURE_EVIDENCE` (the trusted reference fixture demonstrated suite behavior but did not provide arbitrary Candidate App evidence). Multiple provisions are retained and displayed together. Independent report verification recomputes the provisions from the bound evidence environment and rejects removed, added, or altered provisions.

Clearing a provision requires the stated follow-up evidence, not a change to an already truthful passing row. The report identifies whether the affected rows can be rerun rather than implying that unrelated compatibility behavior failed.
