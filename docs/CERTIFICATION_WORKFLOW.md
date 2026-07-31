# Certification workflow

This guide describes the public TestKit workflow. It does not define fees,
trademark rights, appeals, service levels, or other certification-authority
policy.

## 1. Identify the exact target and profile

Choose one target form:

- `--manifest-url`: published CanApp descriptor;
- `--server-base-url`: owner-controlled CanApp publication root;
- `--apk-only --apk`: raw native APK without a discovery surface;
- `--fixture-dir`: TestKit demonstration only, never arbitrary-CanApp
  certification.

Choose `PROFILE-WEB`, `PROFILE-NATIVE_ANDROID`,
`PROFILE-SUITE_QUALITY`, or `PROFILE-CLAIMED_FUTURE`. Bind the exact APK where
native or publication identity matters.

## 2. Run the complete profile

Use `respect-ification full-test`, which delegates to the unchanged Test Suite
and preserves its verdict and exit code:

```sh
respect-ification full-test \
  --manifest-url https://owner.example/canapp/manifest.json \
  --profile PROFILE-WEB \
  --output-dir /absolute/path/to/run
```

Use a fresh output directory. Certification mode generates a fresh challenge.
Do not supply diagnostic fixture results, owner-authored outcomes, or a
deterministic seed as certification evidence.

## 3. Read attribution before remediation

The text report summarizes each row. The JSON report is authoritative. Follow
the typed routing described in [ROLES_AND_RESPONSIBILITIES.md](ROLES_AND_RESPONSIBILITIES.md).

CanApp failures enter the RESPECT-ification workflow. External dependencies,
TestKit gaps, harness incidents, RESPECT Platform observations, and
specification blocks retain their own owners.

## 4. Repair the CanApp and owner harness

Follow [RESPECTIFICATION_WORKFLOW.md](RESPECTIFICATION_WORKFLOW.md). The
generated prompt may repair normal production code, build logic, tests, and
genuinely external publication harnesses. It must update `Human_ToDo.md` with
only remaining human work.

## 5. Establish a truthful lesson inventory

The repair adapter contains source-derived candidates. A human or AI must
trace the production selector and loader and create a complete inventory:

```json
{
  "artifact_type": "respect_confirmed_lesson_inventory",
  "format_version": "1.0.0",
  "source_tree_digest": "COPY_FROM_REPAIR_ADAPTER",
  "inventory_complete": true,
  "default_source_path": "relative/path/to/default.lesson",
  "lessons": [
    {
      "source_path": "relative/path/to/default.lesson",
      "sha256": "COPY_CURRENT_FILE_SHA256",
      "title": "Truthful lesson title"
    }
  ]
}
```

Every path must be a real source-derived candidate, every digest must match
current bytes, and every title must be established from source or owner facts.

Generate the normalized manifest:

```sh
respect-ification publication-manifest \
  --repair-adapter /absolute/path/to/repair-adapter.json \
  --source-root /absolute/path/to/source-collection \
  --canapp-identifier https://owner.example/canapps/example \
  --canapp-title "Example CanApp" \
  --application-id example.owner.canapp \
  --public-path /example \
  --launch-path-prefix /example/launch/ \
  --lesson-identifier-root https://owner.example/lessons \
  --lesson-media-type application/vnd.example.lesson \
  --lesson-inventory /absolute/path/to/lesson-inventory.json \
  --output /absolute/path/to/publication-manifest.json
```

These identity values are owner facts. Do not copy the example values.

## 6. Create and verify a provisional publication

For local work, a debug signer and local origin are allowed but remain
provisional:

```sh
respect-ification publication-pack \
  --manifest /absolute/path/to/publication-manifest.json \
  --source-root /absolute/path/to/source-collection \
  --origin https://canapp.local.example:8765 \
  --signing-fingerprint OWNER_SUPPLIED_SHA256_FINGERPRINT \
  --signer-kind debug \
  --provision provisional \
  --output /absolute/path/to/provisional-pack
```

Serve it with an explicitly trusted local certificate:

```sh
respect-ification publication-serve \
  --pack /absolute/path/to/provisional-pack \
  --bind 127.0.0.1 \
  --port 8765 \
  --certfile /absolute/path/to/server.pem \
  --keyfile /absolute/path/to/server-key.pem
```

Verify local structure and deployed HTTP behavior:

```sh
respect-ification publication-verify \
  --pack /absolute/path/to/provisional-pack \
  --deployed-origin https://canapp.local.example:8765 \
  --ca-cert /absolute/path/to/local-ca.pem \
  --receipt-output /absolute/path/to/provisional-verification.json
```

## 7. Add native Android runtime evidence

Build the suite-owned companion as documented in
[NATIVE_ANDROID_RUNTIME_DRIVER.md](respect_compat/NATIVE_ANDROID_RUNTIME_DRIVER.md),
then supply the APK, receipt, selected device, and bounded scenario as one
atomic runtime group.

Emulator evidence remains attributable but may carry
`EMULATED_ANDROID_RUNTIME`. Clearing it requires the provision's named
physical-device rerun.

RESPECT-owned Android observations use the separate
[RESPECT Platform emulator provider](respect_compat/RESPECT_PLATFORM_EMULATOR_PROVIDER.md).

## 8. Prepare production publication

A production pack requires:

- the exact submitted APK;
- release signing;
- a stable owner-controlled HTTPS origin;
- production classification;
- deployed-origin verification;
- immutable exact-build acquisition;
- publication authorization;
- the source-locked Spix certification trust anchor for final Foundation
  certification.

Generate the production pack using `--apk` rather than a disconnected manual
fingerprint:

```sh
respect-ification publication-pack \
  --manifest /absolute/path/to/publication-manifest.json \
  --source-root /absolute/path/to/source-collection \
  --origin https://owner.example \
  --apk /absolute/path/to/exact-submitted.apk \
  --signer-kind release \
  --provision production \
  --publication-authorization-token /absolute/path/to/spix-token.json \
  --output /absolute/path/to/production-pack
```

Production pack creation rejects local origins, IP-address origins, debug
signers, package mismatches, and a manual fingerprint not bound to the APK.
Run `publication-verify --deployed-origin` against the deployed production
origin.

## 9. Obtain publication authorization

Only use a real service URL and owner-approved publisher facts:

```sh
respect-ification publication-authorization \
  --spix-service-url https://spix.example/service \
  --publisher-id OWNER_PUBLISHER_ID \
  --agreement-version OWNER_AGREEMENT_VERSION \
  --app-id OWNER_APP_ID \
  --artifact /absolute/path/to/exact-submitted.apk \
  --immutable-artifact-url https://owner.example/builds/SHA256/canapp.apk \
  --state /absolute/path/to/private/authorization-state.json \
  --token-output /absolute/path/to/private/spix-token.json
```

The example domain is not a production endpoint. Pending runs return 2 and
reuse the same state. `--open-signing` may open the current signing flow.
Replacing a terminal request requires explicit
`--replace-terminal-request`.

## 10. Rerun and hand back

Run the complete selected profile against the exact deployed target and exact
submitted artifact, supplying its immutable URL and publication token where
applicable. Preserve all emitted artifacts. Report:

- exact verdict and exit code;
- target and Matrix hashes;
- remaining provisions;
- responsible party and clearance for each;
- affected-row or full-profile rerun requirement.

No publication pack or authorization token can override a non-passing Test
Suite result.
