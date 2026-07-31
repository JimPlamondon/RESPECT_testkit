# Contributing

This repository uses task branches, pull requests, active repository-local hooks, and Developer Certificate of Origin sign-off on authored commits.

Do not commit secrets, private Prep output, hidden certification fixtures, anti-gaming inputs, Candidate App packages, Android Package Kit files, device evidence, caches, or generated run reports.

Contributions must preserve the Test Suite as the sole compatibility-verdict authority, the Kit as a non-certifying repair workflow, and the canonical Matrix as one maintained runtime authority.

Create an isolated development environment and run the suite:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
pytest -q
respect-matrix-validate --self-test --require-ready
python tools/validate_migration_manifest.py \
  --manifest migration/source_manifest.json
```

Install the repository-local hooks with `tools/install_git_hooks.sh`. Run
`reuse lint`, build the wheel, and run `tools/inspect_distribution.py` against
that wheel when changing packaging or release contents.

Documentation commands and JSON examples must be exercised against the
current implementation. Do not document a certification policy, production
service endpoint, support commitment, or owner fact that the repository does
not establish.
