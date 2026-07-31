# Roles and responsibilities

The TestKit separates the owner of a requirement from the actor controlling a
particular observation. A non-final certification run is not automatically a
CanApp failure.

| Role | Owns | Must not be assigned |
|---|---|---|
| CanApp artifact owner | Production CanApp code, build, manifest, launch, loading, lifecycle, cache, and xAPI behavior | RESPECT, TestKit, publisher, or Foundation defects |
| App developer harness | Owner-controlled provisioning, publication, and operational test environment | TestKit actor malfunctions |
| Publisher | Legal publication authorization and immutable exact-build hosting | CanApp implementation behavior |
| Spix Foundation | Certification trust anchor and Foundation-controlled authorization | Submission-supplied trust |
| RESPECT Platform team | Real launcher and service behavior | CanApp repair tasks |
| TestKit team | Observers, actors, Matrix execution, reporting, and suite capability | Target blame when no observation exists |
| TestKit operator | Healthy execution of suite-owned actors and the selected environment | Changing the Matrix or verdict |
| Certification authority | Approved evidence environment, physical-device confirmation, and final program actions | Repairing the CanApp |
| Specification authority | Decisions where required behavior is undefined | Engineering a guessed requirement |
| Human in the Loop | Facts, consent, credentials, approvals, physical access, and decisions automation cannot supply | Repeating work already delegated to the prompt |
| Code-capable AI | Safe inspection, execution, CanApp/harness repair, verification, and accurate handback | Inventing authority or claiming certification |

## Result routing

| Observed result | Meaning | Normal next owner/action |
|---|---|---|
| `pass` | Required behavior was affirmatively established | None |
| `canapp_implementation_fail` | Attributable CanApp-controlled defect | CanApp repair through the Kit |
| `code_compatible_through_substitute` | Covered behavior passed through a fidelity-bounded substitute | Promote against the real dependency |
| `unmeasured_external_dependency` | Required external condition was unavailable | Provision or observe it |
| `testkit_capability_gap` | The TestKit lacks an adequate observer | TestKit engineering |
| `harness_error` | A suite-owned actor malfunctioned | Operator diagnostic incident |
| `respect_platform_gap` | Qualifying real-platform evidence failed | RESPECT Platform team |
| `specification_blocked` | Required behavior is unresolved | Specification decision |
| `not_applicable` | The row does not apply | None |

Only `canapp_implementation_fail` authorizes a `kit_task`.
