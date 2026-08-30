# Deployment and source-integrity runbook

This is the canonical deployment document. It defines how a future candidate is
qualified, tied to an exact source revision, released, verified, and rolled
back. It does not assert that any public URL currently serves this checkout.

Architecture belongs in [ARCHITECTURE.md](ARCHITECTURE.md), operational limits in
[LIMITATIONS.md](LIMITATIONS.md), and historical checkpoint identities in the
[execution ledger](evidence/EXECUTION_LEDGER.md).

## Evidence boundary

The repository contains a deployable Next.js frontend and a separately
containerized FastAPI reference service. Deployment is an owner-authorized
external action; checked-in workflows verify candidates but do not publish them.

Available evidence does not independently bind a public dashboard response to
the current repository source. Therefore:

> Deployed source SHA not independently verifiable from available evidence.

A reachable page, matching appearance, provider alias, or previously documented
deployment command is not source linkage. Historical public-URL observations
remain preserved in
[MT9_RELEASE_FREEZE.md](evidence/MT9_RELEASE_FREEZE.md#4--deployment-relationship)
and the
[claim-to-evidence matrix](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#8--deployment-status).
They are not repeated here as current status.

No public backend is established by the repository record. Model bundles remain
local ignored artifacts unless a separately reviewed private artifact-delivery
design is approved.

## Release units

| Unit | Repository source | Required release identity | Data boundary |
| --- | --- | --- | --- |
| Reviewer frontend | `web/` plus committed exported aggregate data | Git commit, `web/` tree, dependency lock, build configuration, immutable provider deployment ID | No rows or model bytes |
| Reference API image | `Dockerfile`, `api/`, packaged runtime | Git commit, image digest, platform, SBOM, scan evidence | No embedded model or dataset |
| Model bundle | Reviewed local bundle manifest and payloads | Manifest hash plus every payload hash | Private, read-only delivery only |

These units must be versioned independently. A frontend deployment never proves
that a backend or model was deployed.

## Local release-candidate gates

Run from a clean checkout of the exact proposed commit with no untracked test or
build input:

1. Record `git rev-parse HEAD`, `git status --short`, `git rev-parse HEAD^{tree}`,
   and `git rev-parse HEAD:web`.
2. Install only from the committed hash-locked Python requirements and npm
   lockfile in isolated environments.
3. Run the data-free quality sequence in
   [REPRODUCIBILITY.md](REPRODUCIBILITY.md#data-free-deterministic-checks).
4. Build the frontend with the exact intended public environment. Record names
   and non-secret values that are compiled into browser code.
5. For an API candidate, build the pinned `linux/amd64` image and run the
   liveness, readiness, model-info, synthetic inference, restricted-runtime,
   vulnerability-scan, and SBOM gates in [CONTAINER.md](CONTAINER.md).
6. For a real candidate bundle, require exact artifact provenance,
   direct/single/batch parity, monitoring reference data, and a named rollback
   bundle. Historical evaluation alone is not authorization to serve a model.
7. Repeat the release gate without source changes and investigate any material
   output or test drift.

Any failed or skipped required gate leaves the candidate unreleased.

## P0.5 deployment-to-source-SHA integrity

P0.5 must establish a two-sided cryptographic and provider-recorded link. The
procedure is deliberately stricter than observing an HTTP 200 response.

### 1. Freeze the candidate

Record, before deployment:

```bash
git status --short
git rev-parse HEAD
git rev-parse HEAD^{tree}
git rev-parse HEAD:web
shasum -a 256 web/package-lock.json web/public/data/dashboard.json
```

The worktree must be clean or the deployment must stop. Do not infer the content
of a dirty build from `HEAD`.

Create a small public release manifest during the authorized P0.5 change. It
must contain only non-secret identifiers:

- schema version;
- exact Git commit SHA;
- exact `web/` tree SHA;
- dashboard-export SHA-256;
- dependency-lock SHA-256; and
- build mode and public API-origin state.

The manifest must be part of the source commit being deployed. It must not be
generated after the commit or injected only through an editable provider field.

### 2. Build and verify locally

Run the frontend test, lint, type, build, and browser gates from that commit.
Verify that the built application exposes the release manifest and that its
values match the recorded Git and file digests.

Keep the build log, command exit codes, runtime versions, and a digest of the
deployable output or provider upload bundle. Build timestamps alone are not
identity evidence.

### 3. Create an immutable preview deployment

Deploy to a new immutable provider deployment, not directly to the public alias.
Record:

- provider project ID;
- immutable deployment ID and URL;
- provider-reported Git source SHA, if available;
- uploaded artifact/output digest, if available;
- build environment and public environment names; and
- creation time as supporting context, not primary identity.

If the provider cannot report a source SHA or immutable artifact identity, the
served release manifest becomes mandatory and the limitation must remain
explicit. Do not guess from an alias or visual match.

### 4. Verify from outside the build environment

Using read-only requests against the immutable preview URL:

1. require successful responses for `/`, `/evidence`, and the release manifest;
2. compare the served commit, `web/` tree, dashboard digest, and lock digest with
   the frozen candidate;
3. inspect security headers and confirm that browser-visible configuration
   contains no credential;
4. verify that `/demo` is unavailable unless the intended, reviewed local/public
   API boundary is explicitly configured;
5. run the reviewer-critical mobile, keyboard, disclosure, and evidence checks;
6. compare provider-reported source metadata with the served manifest; and
7. retain the immutable deployment URL and response digests in the release
   evidence record.

Any mismatch is a `NO-GO`. A matching page title or metric is not an acceptable
substitute.

### 5. Promote only after linkage passes

Alias promotion is a separate owner-authorized action. Promote only the exact
immutable deployment verified above. Immediately repeat the served-manifest and
critical-route checks through the alias and confirm they resolve to the same
immutable deployment ID.

Update the claim-to-evidence matrix and execution ledger with the verified
commit, tree, deployment ID, immutable URL, alias, command results, and evidence
digests. Only then may documentation call that URL the candidate dashboard.

## API rollout boundary

A future public API requires a separate provider and security decision. Before
traffic, it needs at minimum:

- provider-supported `linux/amd64` image execution by immutable digest;
- private read-only delivery of one reviewed bundle manifest;
- TLS termination, authentication, authorization, rate limiting, and body
  limits with named ownership;
- redacted logging and audit retention controls;
- capacity, cold-start, timeout, and failure measurements in that provider;
- durable idempotency/audit design appropriate to worker count;
- monitoring, incident response, and rollback ownership; and
- explicit approval for cost and retention.

Local loopback benchmarks cannot satisfy these gates.

## Rollback

Keep the last verified immutable frontend deployment, API image digest, and
bundle manifest available. Rollback means routing to those exact identities—not
rebuilding an old branch.

After rollback:

1. verify the frontend release manifest through the public route;
2. verify API liveness, readiness, model-info, and one golden synthetic request;
3. confirm the audit sink is healthy before releasing an inference result;
4. check that the restored bundle and image match their recorded digests; and
5. preserve redacted incident evidence without rewriting historical records.

Provider-specific routing and DNS commands must be added only after a provider
is selected and rehearsed.

## Evidence to retain

For each authorized release, retain a concise record containing:

- candidate commit and source-tree identities;
- working-tree cleanliness;
- dependency and exported-data digests;
- exact verification commands and exit codes;
- provider project and immutable deployment identities;
- served release-manifest response and digest;
- security-header and route results;
- image digest, platform, scan, and SBOM when an API is involved;
- rollback identities and rehearsal result; and
- approval for promotion.

Do not place credentials, raw provider environment values, model bytes, private
artifact URLs, or customer data in that record.
