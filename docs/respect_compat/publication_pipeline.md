# Certified-build publication prerequisites

Passing the Candidate App requirements is necessary but not sufficient for the
Spix Foundation to publish a build in the global RESPECT Compatible app
registry. Two publisher-owned prerequisites complete the automated handoff.

`PUBLISH-001` requires a Spix-issued publication-authorization token. The token
is signed by Spix and binds the publisher, stable app identifier, exact
submitted-artifact SHA-256 digest, immutable artifact URL, Publisher Agreement
version, DocuSign envelope reference, issue time, token identifier, and
`registry:publish-if-certified` scope. The signed Publisher Agreement is the
legal record. DocuSign access and refresh tokens remain Spix secrets and are
never placed in a TestKit bundle.

`PUBLISH-003` is owned by the Spix Foundation. It requires the Test Suite to
contain a source-locked Spix Ed25519 public key independently of anything
provided by the Candidate App publisher. A key supplied with the submission is
an untrusted substitution and cannot satisfy this row.

Until Spix publishes that key, the Test Suite generates one local Ed25519
keypair and reuses it on subsequent runs from its suite-controlled state
directory. The private key is stored with owner-only permissions and never
appears in reports or submission bundles. The suite may issue a testing-only
authorization with that private key to exercise the complete token path, but
`PUBLISH-003` remains incomplete and approval is explicitly
`Provisional (RESPECT certification key is testing-only)`. The state directory
can be fixed in continuous integration with
`--certification-key-state-dir`; otherwise it is placed beside the run-output
directories.

The Kit treats agreement signing as an asynchronous idempotent operation. Its
operation is “ensure the agreement for this publisher and agreement version,”
not “create another envelope.” Local state contains only public request,
envelope, status, and token-file references. A pending rerun checks the existing
request and does not reopen the signing page. Declined, voided, or expired
requests require explicit human approval before replacement. Once the master
agreement is complete, Spix can issue build-specific authorization tokens under
that agreement without requesting another signature.

`PUBLISH-002` requires a content-addressed HTTPS URL whose path contains the
exact submitted artifact’s SHA-256 digest. The Test Suite independently fetches
that URL, requires a successful response with `Cache-Control: immutable`, and
compares the returned bytes with the artifact that it tested.

If either publisher prerequisite is absent, Candidate App results remain intact but
approval is capped at `Provisional (publication authorization missing)` or
`Provisional (immutable certified-build URL missing)`. A malformed or
mismatched token, or an acquisition URL that returns different bytes, fails its
publisher-owned Matrix row. Neither outcome is represented as a Candidate App
code defect, and the RESPECT-ification repair prompt must not invent evidence
or modify the app to conceal it.

When the Spix trust anchor is absent, the testing-key provision applies in
addition to any publisher provisions. Publishing and source-locking the real
Spix key clears only `PUBLISH-003`; it does not excuse a missing legal
authorization or immutable artifact.
