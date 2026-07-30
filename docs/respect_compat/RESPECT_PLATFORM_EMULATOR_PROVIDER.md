<!--
SPDX-FileCopyrightText: 2026 Jim Plamondon
SPDX-License-Identifier: Apache-2.0
-->

# RESPECT Platform emulator provider

The Test Suite can run the RESPECT-owned Native Android Matrix rows against
the real RESPECT Platform application on a selected Android emulator. This
closes the old `reference RESPECT runtime observation` capability gap without
turning a RESPECT Platform failure into a Candidate App failure.

## Inputs

Add these arguments to `respect-compat` or `respect-ification full-test`:

```text
--device-id <emulator serial>
--respect-platform-apk <respect.apk>
--respect-platform-build-receipt <receipt.json>
--respect-platform-scenario <scenario.json>
```

Generate the build receipt with:

```text
respect-platform-receipt \
  --apk <respect.apk> \
  --source-root <clean RESPECT checkout> \
  --output <receipt.json>
```

The receipt binds the exact APK digest and Android package to the clean
RESPECT source revision. The suite verifies that binding, verifies that the
selected Android Debug Bridge target is an emulator, and installs that exact
APK before starting the provider.

## Scenario and provider boundary

The scenario is a JSON object:

```json
{
  "artifact_type": "respect_platform_emulator_scenario",
  "format_version": "1.0.0",
  "respect_package": "world.respect.app",
  "canapp_package": "org.jims.mobilekb",
  "provider_command": ["respect-platform-adb-provider"],
  "selected_rows": [
    "AUTH-002",
    "LAUNCH-001",
    "LAUNCH-009"
  ],
  "row_devices": {
    "LAUNCH-009": "emulator-5556"
  },
  "row_workflows": {
    "AUTH-002": {
      "actions": [
        {
          "type": "command",
          "capture": "invalid_request",
          "argv": ["./probe-invalid-auth"],
          "parse": "json"
        }
      ],
      "observation": {
        "missing_status": {
          "capture": "invalid_request.stdout.missing_status"
        }
      }
    }
  },
  "timeout_seconds": 900
}
```

`respect-platform-adb-provider` is the suite-shipped action runner. Its
per-row workflows execute argument-array commands, make controlled HTTP
requests, read JSON evidence files, and extract regular-expression captures.
Observation fields are projected from those captures. This lets a deployment
use Maestro, Android Debug Bridge UI automation, the RESPECT end-to-end
database export, controlled publication-server request logs, and Android
activity/log observations without moving the Matrix oracle into a shell
script. The suite supplies the following environment variables:

- `RESPECT_TESTKIT_CHALLENGE`
- `RESPECT_TESTKIT_TARGET_DIGEST`
- `RESPECT_TESTKIT_DEVICE_ID`
- `RESPECT_TESTKIT_RESPECT_APK`
- `RESPECT_TESTKIT_RESPECT_APK_SHA256`
- `RESPECT_TESTKIT_RESPECT_PACKAGE`
- `RESPECT_TESTKIT_CANAPP_PACKAGE`
- `RESPECT_TESTKIT_SCENARIO`
- `RESPECT_TESTKIT_ROW_DEVICES`

Each workflow also receives `RESPECT_TESTKIT_ROW_ID` and
`RESPECT_TESTKIT_ROW_DEVICE_ID`, so its `adb -s` actions address the emulator
assigned to that row. Unmapped rows use the primary `--device-id`.

Multiple emulator assignments are necessary for the complete launch-policy
set: `LAUNCH-001` requires Android 30 or later, while `LAUNCH-009` requires
Android 29 or earlier. The suite probes every assigned emulator, installs the
same receipt-bound RESPECT APK on each, and binds every row to that device's
measured environment. A workflow's claimed API level must match the actual
emulator probe.

The command must emit exactly one
`respect_platform_raw_observations` JSON object on standard output. Its
challenge, target digest, emulator serial, APK digest, RESPECT package,
Candidate App package, and selected row set must exactly match the active
run. This rejects stale or cross-target evidence.

The provider supplies raw observations, not verdicts. The Test Suite owns and
executes the pass/fail oracle for every supported row. It presently has
oracles for the 13 RESPECT-owned rows selected by the Native Android profile:

- `AUTH-002`
- `LAUNCH-001`, `LAUNCH-002`, and `LAUNCH-009`
- `OFFLINE-001` and `OFFLINE-002`
- `REG-001` through `REG-005`
- `XAPI-012` and `XAPI-020`

Each oracle also has an isolated-fault negative test. A provider cannot turn
an incomplete observation into a pass by including a claimed `state`.

## Result routing

Passing observations become real, suite-controlled
`environment_observation` evidence. A failed oracle remains owned by
`respect_launcher` or `respect_service` and routes as RESPECT Platform
evidence; it never creates a Candidate App repair task. Emulator evidence is
still reported with the existing `EMULATED_ANDROID_RUNTIME` certification
provision.
