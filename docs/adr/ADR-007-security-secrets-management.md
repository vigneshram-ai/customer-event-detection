# ADR-007: Security and Secrets Management

**Status:** Accepted
**Date:** 2026-09-15 (Milestone 13)

## Context

The project runs on Databricks Free Edition — a single-workspace environment
with no Azure subscription and no CI/CD credential flow yet (CI/CD is
deferred to Milestone 14). Security was explicitly deferred from earlier
milestones ("revisit later"). Several assumptions had accumulated in
`docs/current-context.md`'s Known Gaps section, most notably that
`ced.training` access restricted to a training-job identity was **cannot be
enforced on Free Edition (single-user)**.

This ADR documents what was actually tested against the live Free Edition
workspace — not inferred from general Databricks documentation, which
mostly describes Premium/Enterprise-tier or standard-tier behavior — across
three areas: secrets management, RBAC, and audit logging. Consistent with
the project's verification discipline (established since Milestone 12's
serverless-compute finding), every claim below is backed by a command run
and output observed during this milestone, not assumed from docs.

## Options Considered

For each area, the real question was not "what should the design be" but
"what does Free Edition actually permit" — so the primary work this
milestone was empirical probing, with design decisions following from the
results rather than preceding them.

**Secrets:** `.env` file (status quo) vs. Databricks-backed secret scope vs.
Azure Key Vault–backed scope (rejected outright — no Azure subscription).

**RBAC:** assume single-user and design around it (status quo assumption)
vs. empirically test grant/revoke/service-principal support before
accepting the limitation.

**Audit:** assume unavailable on Free Edition (status quo assumption) vs.
test `system.access.audit` directly.

## Decision & Findings

### 1. Secrets management — Databricks secret scopes

**Verified (IMPLEMENTED & VERIFIED, scope-limited):**
`databricks secrets create-scope`, `put-secret`, `list-secrets`, and
in-notebook retrieval via `dbutils.secrets.get()` all work correctly on
Free Edition. Notebook cell output automatically redacts retrieved secret
values (`print(value)` renders `[REDACTED]`, not the real string), and
`len(value)` on the redacted value still returns the true length —
confirming the redaction is a display-layer control, not truncation.

**Decision: the project's PAT remains in `.env` (gitignored) and Airflow's
Fernet-encrypted connection store. It is not migrated to a Databricks
secret scope.**

**Rationale:** `dbutils.secrets.get()` is only reachable from *within* the
Databricks runtime — a notebook or job already executing on Databricks
compute. The PAT's actual job is the opposite: it lets *external* processes
— local `databricks-sdk` scripts running on Windows, and Airflow's
`DatabricksSubmitRunOperator` running in WSL2 — authenticate *to*
Databricks in the first place. Fetching that credential from a
Databricks-hosted secret scope would require already being authenticated to
Databricks, which is circular. No secrets manager, on any platform, can
hand you the key that unlocks the secrets manager itself. This is a genuine
architectural constraint, not an unexplored option or a missed
configuration step.

The secret scope (`ced-secrets`) remains created and validated —
appropriate infrastructure for a credential a *notebook* needs mid-execution
(e.g. a third-party API key called from inside a pipeline notebook). No
such use case currently exists in this project. The scope is documented as
available, working, unused infrastructure rather than force-fit onto a
mismatched use case.

**Verification commands (abbreviated):**
```bash
databricks secrets create-scope ced-secrets
databricks secrets put-secret ced-secrets test-key3 --string-value "hello-world"
databricks secrets list-secrets ced-secrets
```
```python
# in a Databricks notebook
from databricks.sdk.runtime import dbutils

value = dbutils.secrets.get(scope="ced-secrets", key="test-key3")
print(f"Retrieved length: {len(value)}")  # -> 11 (correct)
print(value)  # -> [REDACTED]
```

### 2. RBAC — Unity Catalog grants

**Verified (IMPLEMENTED & VERIFIED — reverses a prior documented
assumption):**

| Test | Result |
|---|---|
| `GRANT SELECT` to a nonexistent principal | Correctly rejected: `PRINCIPAL_DOES_NOT_EXIST` |
| `GRANT SELECT` to a real human user | Succeeded, visible in `SHOW GRANTS` |
| Create a service principal via workspace UI | Succeeded — Application Id issued, OAuth client secret generated |
| `GRANT SELECT` to SP without `USE CATALOG`/`USE SCHEMA` | Correctly rejected until the full grant chain was applied |
| SP authenticates via OAuth client credentials, reads `ced.training` | Succeeded (`GET /api/2.1/unity-catalog/schemas/ced.training` → 200) |
| Same SP attempts to read `ced.bronze` (no grant) | Correctly denied: `User does not have USE SCHEMA on Schema 'ced.bronze'` |
| Same SP reads catalog-level metadata for `ced` (has `USE CATALOG`) | Succeeded |

This directly overturns the assumption, carried since Milestone 1, that
Free Edition is effectively single-user and therefore cannot enforce
per-identity schema isolation. It can: Free Edition supports multiple human
identities and service principals, full `GRANT`/`REVOKE` semantics, and
correct hierarchical enforcement (catalog → schema → object), verified both
positively (SP could read what it was granted) and negatively (SP was
denied what it wasn't).

**Decision: this resolves the `ced.training` isolation gap as
*implementable*, but it is not implemented this milestone.** A real
training-job service principal (`test_sp`, Application Id
`374365a1-96f6-4597-af4c-a82aec75fff6`) exists and was correctly scoped
during verification, but `train_model.py` and
`validate_and_promote_model.py` continue running under the personal
account, unchanged. Migrating the training pipeline to run as this SP is
deferred to a future milestone as a well-understood, low-effort item — not
an open unknown requiring further investigation.

### 3. Audit logging — `system.access.audit`

**Verified (IMPLEMENTED & VERIFIED):** `system.access.audit` is enabled and
populated by default on this Free Edition metastore — no explicit admin
"enable system table schema" step was required, which is notable since
general Databricks documentation describes several system tables as
requiring manual enablement. The table contains structured, detailed
per-event records: account/workspace id, event timestamp, source IP, user
agent, full identity, service name, action name, complete request
parameters, and response status/body. Verified directly against this
project's own activity — the table captured, among other events, the
`GRANT`/`getTable`/`updateTables` calls generated during this milestone's
own RBAC probes, with correct identity attribution.

**Decision:** documented as available, verified infrastructure. No
dashboard, alert, or scheduled query is built against it this milestone —
that is future monitoring-layer work if pursued, not a Milestone 13
deliverable. Retention is regional per Databricks documentation (365-day
free retention window).

## Consequences

- The project's actual security posture is materially stronger than
  previously documented: real hierarchical RBAC, a real audit trail, and
  real secret-scope capability all exist and were verified on Free Edition
  — not assumed, not designed-only.
- None of the three verified capabilities changed runtime behavior this
  milestone. The PAT-in-`.env` / Airflow-connection pattern continues
  exactly as before — now backed by an explicit, reasoned justification
  (the bootstrap-circularity constraint) rather than being an unexamined
  default.
- Prior Known Gaps / Technical Debt entries stating `ced.training` identity
  isolation "cannot be enforced on Free Edition" are factually incorrect
  and are corrected in this milestone's documentation update, not merely
  closed.
- A throwaway service principal (`test_sp`) now exists in the workspace
  with real (if narrow) grants. It is harmless as configured but should be
  either formally adopted (renamed, repurposed) or deleted before the
  project is considered "clean" — flagged, not resolved, this milestone.

## Future Considerations

- Migrate `train_model.py` / `validate_and_promote_model.py` to
  authenticate as the training-job service principal, enforcing the
  isolation in practice rather than only in a verification test.
- Replace the personal-account PAT with SP OAuth client credentials for
  Airflow's `databricks_default` connection and local `databricks-sdk`
  scripts, once a genuine driver exists. This is a distinct decision from
  the secret-scope question addressed above (it changes *what* credential
  is used, not *where* it's stored) and is explicitly not undertaken this
  milestone.
- Build a scheduled query or lightweight dashboard against
  `system.access.audit` as a real monitoring artifact, rather than leaving
  it as verified-but-unused infrastructure.
- **PAT lifecycle risk, surfaced but not fixed this milestone:** the
  project's original PAT had silently expired and was only caught by
  chance during this milestone's CLI-auth probe (`auth profiles` returned
  `Valid: NO`). No expiry alerting or rotation process exists. Both
  `.env` and the Airflow connection were updated reactively once
  discovered. This is a genuine operational gap worth addressing before
  any future milestone that depends on unattended/scheduled execution.
- Formally decide the fate of `test_sp` (rename and adopt, or delete) as a
  cleanup item.