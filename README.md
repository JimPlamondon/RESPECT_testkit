# RESPECT TestKit

`RESPECT-testkit` contains the black-box RESPECT Compatible Test Suite and the
owner-local RESPECT-ification Kit. The Test Suite is the compatibility oracle.
The Kit consumes its immutable artifacts to help repair a Candidate App
(`CanApp`) but cannot change requirements or issue a compatibility verdict.

## QuickStart

Open your Candidate App ("CanApp") project with a code-capable AI and tell that
AI:

> “Install the RESPECT TestKit and apply it to [CanApp]. Follow the TestKit's
> instructions to AIs, perform all code- and harness-level work that you can
> safely perform, and update the generated `Human_ToDo.md` with only the
> actions that I — the Human In the Loop — must do.”

Replace `[CanApp]` with the project name or path. Give the AI shell and
filesystem access to the CanApp, this TestKit, and any device or deployment
environment that it is authorized to use.

The AI must start with [AI_OPERATOR.md](docs/AI_OPERATOR.md). The expected
handback is:

- the exact Test Suite verdict and report path;
- the implementation prompt and current `Human_ToDo.md`, when repair exists;
- a summary of changes and verification performed;
- remaining provisions, responsible parties, and required rerun scope.

Only a complete applicable Test Suite run can certify a CanApp. A generated
prompt, narrow verifier, fixture, local publication, or emulator result is not
by itself certification.

## Documentation

Start at the [documentation index](docs/README.md). It provides separate
routes for a Human in the Loop, a code-capable AI, a TestKit operator, and a
maintainer.

The canonical Compatibility Matrix is bundled once in `respect_compat`.
Requirements owned by RESPECT, the publisher, Spix Foundation, or the TestKit
cannot be reassigned to the CanApp. Future RESPECT Platform upgrade work is
governed by the separate RESPECT Upgrade Dossier; this repository records
neutral platform observations but does not generate platform upgrade work.

This repository is initially private. Package-index publication, tagging,
visibility changes, certification, trademark grants, and registry publication
remain separate owner or certification-authority actions.
