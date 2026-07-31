# Releasing

This extraction supports local source-distribution and wheel construction only.

Run the full tests, Matrix self-tests, manifest validation against the frozen JiMS source, REUSE licensing validation, wheel-content inspection, and isolated installed-wheel acceptance before treating a build as releasable.

The repository tools are the command authority:

```sh
pytest -q
respect-matrix-validate --self-test --require-ready
python tools/validate_migration_manifest.py \
  --manifest migration/source_manifest.json
reuse lint
python -m build
python tools/inspect_distribution.py dist/*.whl
```

Then install the wheel into a new temporary virtual environment and run the
entry-point and installed-smoke commands as shown in
`.github/workflows/checks.yml`. Do not run installed-wheel acceptance from the
source checkout or with `PYTHONPATH` set.

Refresh migration destination hashes only after reviewing intentional
destination changes:

```sh
python tools/refresh_migration_destination_hashes.py \
  --manifest migration/source_manifest.json \
  --repository-root .
```

Publishing to a package index, creating tags, signing releases, changing repository visibility, or granting certification and trademark rights requires a separate owner action.
