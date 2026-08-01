# Native Android runtime driver

The native Android runtime driver is the Test Suite-owned controller for the 26 `PROFILE-NATIVE_ANDROID` Matrix rows that require attributable device behavior. It consists of a clean-room Android xAPI companion application, a separate bounded-gesture injector, and a Python Android Debug Bridge (ADB) controller.

The RESPECT-ification Kit's general `repair-plan` command is documented separately. It may identify native Android implementation seams, but the Test Suite runtime driver contains no proprietary lesson-format knowledge.

The companion application exports the `org.openeel.action.xapioveripc` Android Messenger service. It captures binding, request, correlated reply, flow, completion, and unbind observations and returns controlled statement responses. The separate gesture application injects a declared continuous touch stroke through Android instrumentation and records the resolved pixel path. Keeping gesture injection out of the xAPI companion prevents instrumentation startup from replacing the service process. The Python controller installs the submitted Android Package Kit (APK) and both suite applications, launches the submitted production Hypertext Transfer Protocol Secure (HTTPS) App Link, drives only bounded scenario actions, reads the private event logs through `run-as`, verifies health and artifact bindings, and projects row observations itself.

The companion returns one controlled transient server failure for the first ordinary statement submission. A conforming CanApp must retry the same durable statement without changing its identifier or content. The companion then accepts that identical retry. This exercises idempotent retry behavior without asking a conforming CanApp to manufacture a conflicting statement. If a CanApp does reuse an identifier with different content, the companion returns `409 Conflict` and the Test Suite records the violation.

An owner-authored result file, fixture assertion, raw shell command, imported pass flag, or substituted suite APK cannot become trusted evidence. The controller requires one build receipt binding both suite APK hashes to the driver source packaged with the running Test Suite. It binds observations to the target digest, CanApp APK digest, both suite APK digests, selected device, fresh scenario nonce, CanApp package, and canonical action hashes.

## Build the suite-owned companion

Run:

```sh
respect-runtime-driver-build \
  --gradle-wrapper <path-to-gradlew> \
  --output-apk <driver.apk> \
  --output-gesture-apk <gesture.apk> \
  --receipt <driver.receipt.json> \
  --offline
```

The supplied Gradle wrapper is used only to build the source packaged with the Test Suite; the build command does not import Candidate App code into either suite APK. If `--output-gesture-apk` is omitted, the builder writes `<driver-stem>-gesture.apk` beside the driver.

## Runtime interface

Add `--apk <canapp.apk> --device-id <serial> --runtime-driver-apk <driver.apk> --runtime-driver-receipt <driver.receipt.json> --runtime-scenario <scenario.json>` to `respect-compat`, `respect-ification verify`, or `respect-ification full-test`. The three runtime-driver arguments are an atomic group and require both the submitted APK and an explicitly selected healthy device. A scenario containing `stroke` also requires `--runtime-gesture-apk <gesture.apk>`.

For a Kit-emitted provisional HTTPS origin signed by a local certification authority, add `--ca-cert <authority.pem>`. Certificate-chain and hostname validation remain enabled; the option only supplies the explicit local trust anchor to descriptor, catalog, publication, resource, and runtime discovery requests.

The scenario is owner-local JSON (JavaScript Object Notation) with artifact type `respect_native_android_runtime_scenario`, the CanApp and driver packages, controlled endpoint, authorization, actor, activity identifier, expected production HTTPS launch URL, and a bounded action list. The controller resolves the submitted descriptor and default lesson catalog, selects exactly one publication whose identifier equals the scenario activity identifier, derives the launch base from that publication's single acquisition link, and appends only the standard RESPECT launch parameters. The expected launch URL must exactly match that derived URL. An owner-selected alternate path, hidden diagnostic parameter, invented activity identifier, fragment, or prepopulated reserved parameter is rejected before device mutation.

Scenario format `1.0.0` permits wait, coordinate tap, and the `BACK`, `ENTER`, or `HOME` key events. Format `1.1.0` adds `stroke`. Format `1.2.0` adds `webview_tap`. Arbitrary shell commands and arbitrary JavaScript are rejected.

## Generic stroke vocabulary

A stroke is one uninterrupted `DOWN`, timed sequence of `MOVE` events, and `UP`. It is suitable for tracing, drawing, dragging, handwriting, and other continuous-touch interactions. The TestKit does not describe what a path means to a lesson. The CanApp owner keeps lesson selection, selectors, and path geometry in the owner-local scenario.

Coordinates use integers from `0` through `10000`, normalized to an anchor's bounds. A `foreground_window` anchor uses the active accessibility window. An `element` anchor must resolve to exactly one accessibility node and may combine exact `resource_id`, `class_name`, `text`, and `content_description` selectors. Resolved screen bounds, pixel coordinates, display metrics, action hash, scenario nonce, target package, timing, and injection success are captured in the gesture receipt.

```json
{
  "artifact_type": "respect_native_android_runtime_scenario",
  "format_version": "1.1.0",
  "canapp_package": "org.example.canapp",
  "driver_package": "org.respect.testkit.runtime",
  "launch_url": "https://owner.example/catalog-selected-launch?...",
  "endpoint": "https://controlled-lrs.example/xapi/",
  "auth": "Basic owner-local-control",
  "actor": {"objectType": "Agent", "account": {"homePage": "https://example.invalid", "name": "control"}},
  "activity_id": "https://owner.example/activity",
  "actions": [
    {
      "type": "stroke",
      "anchor": {
        "type": "element",
        "selector": {"resource_id": "org.example.canapp:id/tracing_surface"}
      },
      "points": [
        {"x": 1000, "y": 2000, "at_ms": 0},
        {"x": 3000, "y": 4000, "at_ms": 80},
        {"x": 5000, "y": 6000, "at_ms": 160}
      ]
    }
  ]
}
```

Each stroke has 2–256 points, starts at `at_ms: 0`, uses strictly increasing times no greater than 10 seconds, and stays within its anchor. A scenario is limited to 100 actions, 2048 stroke points, 60 seconds of declared stroke duration, and 60 seconds of waits. Element anchors fail closed when zero or multiple nodes match. The injector also fails if the declared CanApp is not foreground.

The instrumentation component is fixed by TestKit; scenario data cannot select another component or provide a shell command. The build receipt must bind the gesture APK to the running TestKit source. Every action emits started/completed or started/failed records into the mandatory TestKit execution log.

Experience API evidence must result from the catalog-selected lesson's real runtime lifecycle. A successfully injected stroke proves only that the declared touch path was delivered. It does not by itself prove that the lesson recognized the trace or completed. Debug-only triggers, manufactured lesson snapshots, and canned completion sequences are diagnostic evidence and cannot satisfy CanApp conformance rows.

## Generic visible WebView selection

`webview_tap` selects exactly one currently visible Document Object Model element and delivers a real touch at its center through the WebView debugging protocol. The owner-local scenario may combine an exact element tag name, normalized visible text, and one exact attribute name/value pair. TestKit accepts only bounded declarative selector fields; the scenario cannot supply JavaScript, a Cascading Style Sheets selector, a debugging endpoint, or a browser command.

```json
{
  "type": "webview_tap",
  "selector": {
    "tag_name": "example-answer",
    "attribute": {"name": "value", "value": "3"}
  },
  "timeout_ms": 5000
}
```

The action fails closed if the submitted CanApp has no package-bound debuggable WebView, if the package exposes zero or multiple visible pages, or if the selector resolves to zero or multiple visible elements. The per-action timeout is at most 10 seconds and the scenario total is at most 60 seconds. The execution log records a receipt that binds the page origin, hashed page path and title, viewport, element geometry, selector hash, action hash, scenario nonce, and submitted package. Query strings, fragments, visible text, and matched attribute values are not written to the receipt. The selector and expected value remain CanApp-owned facts in the owner-local scenario.

Certification mode still requires the complete selected-profile run. Static APK checks, source inspection, generated prompts, companion builds, and narrow verification remain non-certifying. An attributable emulator run may satisfy the functional Matrix rows it actually exercises, but the overall approval is `Provisional (emulated Android runtime)` until the affected device scenarios are repeated on an approved attributable physical Android device. The report preserves the passing row outcomes and records the emulation provision, affected rows, evidence environment, clearance action, rerun scope, and responsible party separately.
