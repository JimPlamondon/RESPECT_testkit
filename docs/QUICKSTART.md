# AI-first QuickStart

## For the Human in the Loop

Open the CanApp project with a code-capable AI and tell that AI:

> “Install the RESPECT TestKit and apply it to [CanApp]. Follow the TestKit's
> instructions to AIs, perform all code- and harness-level work that you can
> safely perform, and update the generated `Human_ToDo.md` with only the
> actions that I — the Human In the Loop — must do.”

Replace `[CanApp]` with the project name or path. The AI follows
[AI_OPERATOR.md](AI_OPERATOR.md).

Do not work from the generated implementation prompt and `Human_ToDo.md` at
the same time. The prompt owns delegated code and harness work. When it
finishes or becomes blocked, its executor updates `Human_ToDo.md`. The Human
then handles only the remaining approvals, facts, credentials, deployments,
physical-device work, or decisions recorded there.

## Expected handback

The AI should return:

1. The exact Test Suite verdict: `Certified`, `Provisional (...)`,
   `Not certified`, `Incomplete`, or `Non-certification mode`.
2. The absolute path to `respect-report.txt` and `respect-report.json`.
3. The current `Human_ToDo.md`, if repair or human action remains.
4. A concise summary of changes and verification.
5. The remaining provisions, their owners, and the required rerun.

Completing a ToDo or implementation prompt is not certification. Only a
complete applicable Test Suite run is the compatibility oracle.
