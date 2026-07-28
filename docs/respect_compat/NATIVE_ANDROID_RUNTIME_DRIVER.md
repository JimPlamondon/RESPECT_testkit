# Native Android runtime driver

The native Android runtime driver is the Test Suite-owned controller for the 26 `PROFILE-NATIVE_ANDROID` Matrix rows that require attributable device behavior. It consists of a clean-room Android companion application and a Python Android Debug Bridge (ADB) controller.

The RESPECT-ification Kit's general `repair-plan` command is documented separately. It may identify native Android implementation seams, but the Test Suite runtime driver contains no proprietary lesson-format knowledge.

The companion application exports the `org.openeel.action.xapioveripc` Android Messenger service. It captures binding, request, correlated reply, flow, completion, and unbind observations and returns controlled statement responses. The Python controller installs the submitted Android Package Kit (APK) and companion, launches the submitted production Hypertext Transfer Protocol Secure (HTTPS) App Link, drives only bounded scenario actions, reads the companion's private event log through `run-as`, verifies health and artifact bindings, and projects row observations itself.

An owner-authored result file, fixture assertion, raw shell command, imported pass flag, or substituted companion APK cannot become trusted evidence. The controller requires a build receipt binding the companion APK hash to the driver source packaged with the running Test Suite, and it binds observations to the target digest, APK digest, companion digest, selected device, fresh scenario nonce, and CanApp package.

## Build the suite-owned companion

Run `respect-runtime-driver-build --gradle-wrapper <path-to-gradlew> --output-apk <driver.apk> --receipt <driver.receipt.json> --offline`. The supplied Gradle wrapper is used only to build the source packaged with the Test Suite; the build command does not import Candidate App code into the companion.

## Runtime interface

Add `--apk <canapp.apk> --device-id <serial> --runtime-driver-apk <driver.apk> --runtime-driver-receipt <driver.receipt.json> --runtime-scenario <scenario.json>` to `respect-compat`, `respect-ification verify`, or `respect-ification full-test`. The three runtime-driver arguments are an atomic group and require both the submitted APK and an explicitly selected healthy device.

The scenario is owner-local JSON (JavaScript Object Notation) with artifact type `respect_native_android_runtime_scenario`, format version `1.0.0`, the CanApp and driver packages, controlled endpoint, authorization, actor, activity identifier, expected production HTTPS launch URL, and a bounded action list. The controller resolves the submitted descriptor and default lesson catalog, selects exactly one publication whose identifier equals the scenario activity identifier, derives the launch base from that publication's single acquisition link, and appends only the standard RESPECT launch parameters. The expected launch URL must exactly match that derived URL. An owner-selected alternate path, hidden diagnostic parameter, invented activity identifier, fragment, or prepopulated reserved parameter is rejected before device mutation.

Allowed device actions are wait, coordinate tap, and the `BACK`, `ENTER`, or `HOME` key events. Arbitrary shell commands are rejected. Experience API evidence must result from the catalog-selected lesson's real runtime lifecycle; debug-only triggers, manufactured lesson snapshots, and canned completion sequences are diagnostic evidence and cannot satisfy CanApp conformance rows.

Certification mode still requires the complete selected-profile run. Static APK checks, source inspection, generated prompts, companion builds, and narrow verification remain non-certifying. An attributable emulator run may satisfy the functional Matrix rows it actually exercises, but the overall approval is `Provisional (emulated Android runtime)` until the affected device scenarios are repeated on an approved attributable physical Android device. The report preserves the passing row outcomes and records the emulation provision, affected rows, evidence environment, clearance action, rerun scope, and responsible party separately.
