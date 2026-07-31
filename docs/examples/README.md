# Documentation examples

Examples in this documentation use reserved `.example` domains and placeholder
owner facts. Never submit them as production identity or authority.

## Verified smoke run

From a source checkout installed into an active environment:

```sh
respect-compat \
  --fixture-dir src/respect_compat/data/fixtures/v0_1/positive/native_valid \
  --profile PROFILE-SUITE_QUALITY \
  --mode test \
  --run-seed documentation-smoke \
  --output-dir /tmp/respect-documentation-smoke
```

This exercises public fixture and report plumbing in non-certification mode.
It does not certify an arbitrary CanApp.

## Confirmed lesson inventory shape

The example in
[CERTIFICATION_WORKFLOW.md](../CERTIFICATION_WORKFLOW.md#5-establish-a-truthful-lesson-inventory)
comes from the accepted test shape. Replace its source digest, paths, byte
digests, titles, identifiers, package, media type, and origins with facts from
the actual CanApp and repair adapter.

## Runtime examples

The complete RESPECT Platform scenario shape is in
[RESPECT_PLATFORM_EMULATOR_PROVIDER.md](../respect_compat/RESPECT_PLATFORM_EMULATOR_PROVIDER.md).
The native CanApp runtime scenario contract is in
[NATIVE_ANDROID_RUNTIME_DRIVER.md](../respect_compat/NATIVE_ANDROID_RUNTIME_DRIVER.md).

Generated report and prompt examples should come from the current executable
version. Do not maintain hand-edited copies that can drift from schemas and
hash bindings.
