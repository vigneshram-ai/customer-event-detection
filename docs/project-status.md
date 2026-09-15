# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 13_

_Milestone 13 status: IMPLEMENTED AND VERIFIED — security and secrets
management investigated empirically against the live Databricks Free
Edition workspace (not assumed from general documentation). Three areas
probed: Databricks secret scopes, Unity Catalog RBAC, and audit logging.
All three were found to be genuinely functional on Free Edition — notably
better than the assumptions carried since Milestone 1, most significantly
that `ced.training` schema isolation via a dedicated identity was believed
unenforceable on a "single-user" Free Edition and has now been proven
enforceable. No pipeline code changed this milestone — this was a
verification-and-documentation milestone, consistent with the project's
"verify before building" discipline. See ADR-007 for full detail. CI/CD
extension is deliberately deferred to Milestone 14._

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified

**Milestones 1–12** — unchanged from prior status; see git history / earlier
versions of this file for full detail.

**Milestone 13 — Security and secrets management (empirical verification)**

- **Databricks CLI installed and authenticated** — winget install
  (`Databricks.DatabricksCLI` 1.16.1), not on system PATH by default
  (fixed via a permanent User PATH entry). Authenticated via
  `configure --token`. In the process, discovered the project's PAT had
  silently expired (`auth profiles` reported `Valid: NO`) — a real,
  previously-undetected credential lifecycle gap. New PAT generated;
  `.env` and Airflow's `databricks_default` connection both updated.
- **Databricks secret scopes — verified functional.** Created scope
  `ced-secrets`; wrote and read a test secret end-to-end via
  `dbutils.secrets.get()` from a notebook; confirmed automatic redaction
  of secret values in cell output (`print()` shows `[REDACTED]`, `len()`
  still returns the true value length). **Decision: the project's PAT is
  NOT migrated to a secret scope** — `dbutils.secrets.get()` is only
  reachable from inside the Databricks runtime, but the PAT's job is to
  let *external* processes (local scripts, Airflow) authenticate *to*
  Databricks in the first place. This is a genuine bootstrap-circularity
  constraint, not an unexplored option. Full reasoning in ADR-007.
- **Unity Catalog RBAC — verified functional, overturning a prior
  assumption.** `GRANT`/`REVOKE`/`SHOW GRANTS` confirmed working with
  correct principal validation. A service principal was created via the
  workspace UI (Application Id issued, OAuth client secret generated),
  granted a scoped chain (`USE CATALOG` on `ced`, `USE SCHEMA` +
  `SELECT` on `ced.training`), and successfully authenticated
  independently via OAuth client credentials to read `ced.training` —
  while being correctly denied access to `ced.bronze`, a schema it had
  no grant on. This is full positive- and negative-verified hierarchical
  enforcement using a real non-human identity.
- **Audit logging — verified functional.** `system.access.audit` exists,
  is populated by default (no explicit enablement step needed, contrary
  to what general documentation implies for some system tables), and
  captured this milestone's own RBAC probe activity with correct
  identity attribution, full request parameters, and response status.
- **New ADR-007** — "Security and Secrets Management": full findings,
  decisions, and rationale for all three areas above.
- **No runtime/pipeline code changed.** This was a verification and
  documentation milestone. Notebooks, DAGs, and the training pipeline
  continue to run exactly as they did at the close of Milestone 12.

### 🟡 Implemented, Not Fully Verified
- Airflow Fernet key confirmed present (non-default) via a config check;
  full implications not deeply explored this milestone (deliberately kept
  light-touch per user direction).
- **`batch_inference.py`'s exact resolved `model_version` string** —
  inferred, not directly observed (Technical Debt #26). Unaffected by
  Milestone 13.

### 📐 Designed Only
- **Training-pipeline identity migration to the verified service
  principal** — the SP (`test_sp`, Application Id
  `374365a1-96f6-4597-af4c-a82aec75fff6`) is real, correctly scoped, and
  proven functional, but `train_model.py` /
  `validate_and_promote_model.py` still run under the personal account.
  Migrating them is now a well-understood, low-effort future item, not
  an open unknown.
- Replacing the personal PAT with SP OAuth client credentials for
  Airflow's `databricks_default` connection and local scripts — a
  distinct decision from the secret-scope question, not undertaken this
  milestone.
- A scheduled query or dashboard against `system.access.audit` as an
  actual monitoring artifact — the table is verified and populated but
  nothing consumes it yet.
- Time-of-day deviation feature (unchanged, carried from earlier
  milestones).
- Live/shadow evaluation for the champion/challenger pattern (unchanged).
- A genuinely new/unseen event batch for inference (unchanged).
- Full CI/CD extension beyond lint/format/test — deliberately deferred to
  Milestone 14.

### ⏳ Future
- Verifying batch inference's exact `model_version` output string
  directly (Technical Debt #26).
- A genuinely new event batch for batch inference.
- Append/dedup strategy for `ced.inference.detection_results` (Technical
  Debt #24).
- Re-running monitoring against a genuinely new (non-overlapping) batch.
- PAT lifecycle management — no expiry alerting or rotation process
  exists; this milestone's expired-PAT discovery was accidental, not
  detected by any monitoring. A real gap worth addressing before any
  future milestone depends on unattended/scheduled execution.
- Cleanup decision on `test_sp` — rename and formally adopt as the
  training-job identity, or delete it. Currently left in place,
  harmless but unused in production paths.
- Milestone 14 (CI/CD extension) and remaining milestones per the
  approved roadmap.

---

## Current Work
None in progress. Milestone 13 is closed.

## Pending Work
Milestone 14 (CI/CD extension) next, per user direction this milestone.
Milestones 15–23 per the approved roadmap, not yet scoped in detail — do
not begin without explicit user confirmation.

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor`/`SequentialExecutor` for local development | **ADR-009** (original), corrected by **ADR-018** (execution environment) |
| Local→Databricks ingestion via `databricks-sdk` standalone script + Databricks notebook | **ADR-010** |
| Bronze writes use `mode("overwrite")`, not append | **ADR-010** |
| Silver validation is PySpark-native; quarantine failure handling | **ADR-011** |
| Gold window features end at `-1` relative to current row; no quarantine path | **ADR-012** |
| Baseline detector uses fixed, additive point-scoring rules | **ADR-013** |
| Ground truth isolated to `ced.training`, in-memory-only join to features | **ADR-014** |
| Model validation gate: three thresholds, no recomputation; alias-based promotion | **ADR-015** |
| Batch inference scores a reproducible sample of existing Gold data; generic `pyfunc.load_model` + sklearn unwrap for `predict_proba`; `fillna(0)` train/serve parity (scoring matrix only — see ADR-017 correction) | **ADR-016** |
| Monitoring uses Evidently directly (no hand-rolled statistics); auto-selected drift tests (not forced PSI); Milestone 10's batch treated as current-under-monitoring with explicit negative-control framing | **ADR-017** |
| Airflow selected as orchestration layer over no-orchestrator and Databricks Workflows alternatives | **ADR-002** |
| Two-DAG split (inference vs. training), decoupled via the `champion` alias; WSL2-native execution environment; `DatabricksSubmitRunOperator` + multi-task `tasks=[...]` shape required for Free Edition serverless compute | **ADR-018** |
| PAT remains in `.env`/Airflow connection store rather than a Databricks secret scope, due to a bootstrap-circularity constraint; Unity Catalog RBAC (including service-principal identity) empirically confirmed functional on Free Edition, overturning the prior single-user assumption; `system.access.audit` confirmed populated and usable | **ADR-007** (new, Milestone 13) |
| `uv` over Poetry/pip; `ruff` for lint + format | Recorded here only |

---

## Known Issues
- None blocking. CI confirmed green through Milestone 12; unaffected by
  Milestone 13 (no code changes).
- `ced.inference.detection_results`'s persisted feature columns are raw,
  not imputed — Technical Debt #28. Unaffected by Milestone 13.
- Monitoring's `run_id` is a fresh UUID per run — Technical Debt #29.
  Unaffected by Milestone 13.
- **NEW — PAT lifecycle has no monitoring.** The project's original PAT
  silently expired and was discovered only by chance during this
  milestone's CLI-auth setup. No alerting exists for this. Low practical
  risk currently (manual-trigger-only pipelines, frequent hands-on
  development), but a real gap if any future milestone introduces
  scheduled/unattended execution. See ADR-007 Future Considerations.
- **NEW — a throwaway service principal (`test_sp`) exists in the
  workspace** with real, narrow grants (`USE CATALOG` on `ced`,
  `USE SCHEMA` + `SELECT` on `ced.training`). Harmless as configured, not
  referenced by any pipeline, but should be formally adopted or deleted
  as a cleanup item.

## Technical Debt
1–19. Unchanged from Milestone 8 — see prior version of this file / git
history.

~~20. Champion/challenger comparison branch unverified against live
output.~~ **RESOLVED at Milestone 12.**

21–29. Unchanged from Milestone 12 — see prior version of this file.
None resolved or newly introduced by Milestone 13 (this milestone
concerned platform capability verification, not pipeline code).

---

## Corrections to Prior Documentation

Milestone 13 overturned an assumption stated since Milestone 1 and
repeated in every snapshot through Milestone 12:

> ~~`ced.training` schema access restricted to a training-job identity —
> cannot be enforced on Free Edition (single-user).~~

This was **empirically tested and found incorrect**. Free Edition supports
multiple identities (human and service-principal), full `GRANT`/`REVOKE`
semantics, and correctly hierarchical enforcement. The isolation is now
**📐 DESIGNED AND PROVEN FEASIBLE, NOT YET IMPLEMENTED** — a materially
different and more accurate status than "cannot be enforced." See ADR-007.

---

## Environment / Setup Information

| Item | Value | Verification status |
|---|---|---|
| OS | Windows, with WSL2 Ubuntu used for Airflow only | ✅ Verified |
| Project Python (via `uv`) | 3.11.16 | ✅ Verified (unchanged) |
| Airflow Python (WSL2 venv) | 3.12.13 | ✅ Verified |
| Airflow Fernet key | Present, non-default | ✅ Verified (Milestone 13, light-touch check only) |
| `uv` version | 0.12.5 | Stated by user |
| Databricks CLI | 1.16.1, installed via `winget`, added to User PATH | ✅ Verified (Milestone 13) |
| Databricks CLI auth profile | `DEFAULT`, token-based, `Valid: YES` (after PAT rotation) | ✅ Verified (Milestone 13) |
| Git | `main` branch, GitHub remote connected, 2.55.0.windows.4 | ✅ Verified |
| Databricks workspace | Free Edition, `https://dbc-01205ae9-f87b.cloud.databricks.com/`, serverless compute only | ✅ Verified |
| Unity Catalog catalog | `ced` | ✅ Verified |
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold`, `ced.training`, `ced.models`, `ced.inference`, `ced.monitoring` | ✅ Verified |
| Databricks secret scope | `ced-secrets` — created, write/read verified, notebook redaction confirmed | ✅ Verified (Milestone 13) |
| Service principal | `test_sp`, Application Id `374365a1-96f6-4597-af4c-a82aec75fff6`, OAuth client credentials generated, scoped grants on `ced` (`USE CATALOG`) and `ced.training` (`USE SCHEMA`, `SELECT`) | ✅ Verified (Milestone 13) — not adopted into any pipeline yet |
| `system.access.audit` | Populated, regional, 365-day retention (per Databricks documentation) | ✅ Verified (Milestone 13) |
| Unity Catalog model registry | `ced.models.logistic_regression_detector`: v1 → `champion`, v2 → `archived`; `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified (unchanged) |

## Repository Structure (as of Milestone 13)
```text
customer-event-detection/
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore (includes .env)
├── .gitattributes
├── .env (gitignored, not in repo; PAT rotated this milestone)
├── docs/
│ ├── project-status.md
│ ├── current-context.md
│ ├── architecture/ (empty)
│ ├── adr/
│ │ ├── ADR-002-airflow-orchestration-layer.md
│ │ ├── ADR-007-security-secrets-management.md (new, Milestone 13)
│ │ ├── ADR-009 … ADR-017 (unchanged)
│ │ └── ADR-018-milestone-12-orchestration.md
│ ├── security/ (empty — consider moving ADR-007 detail here in future)
│ ├── governance/ (empty)
│ ├── mlops/ (empty)
│ └── nfr/ (empty)
├── data_generation/
├── ingestion/
├── training/
├── notebooks/
│ ├── bronze_ingestion.py
│ ├── silver_transformation.py
│ ├── gold_feature_engineering.py
│ ├── baseline_detector.py
│ ├── load_ground_truth.py
│ ├── train_model.py
│ ├── validate_and_promote_model.py
│ ├── batch_inference.py
│ └── monitoring.py
├── evaluation/
├── data_quality/ (empty)
├── feature_engineering/ (empty)
├── inference/ (empty)
├── monitoring/ (empty — Databricks-only logic, unchanged pattern)
├── data/ (gitignored)
├── airflow/
│ └── dags/
│   ├── ced_inference_pipeline.py
│   └── ced_training_pipeline.py
├── tests/
├── docker/ (empty — Docker no longer used for Airflow, see ADR-018)
└── .github/workflows/ci.yml
```

No files added to the repo this milestone besides `docs/adr/ADR-007-*.md`
and the updated status/context documents. No `pyproject.toml` change — the
Databricks CLI is a standalone binary (winget-installed), not a Python
dependency of any kind, and is not tracked in the project's dependency
files.

## Installed Dependencies

**Production**: `databricks-sdk>=0.133.0`, `python-dotenv>=1.2.3`, `pandas`.
Databricks-side only: `xgboost`, `mlflow`, `evidently`.

**Dev**: `pytest>=8.3.0`, `ruff>=0.6.0`.

**Airflow (WSL2 venv only)**: `apache-airflow==3.3.1`,
`apache-airflow-providers-databricks==7.18.1`.

**Local tooling (not a project dependency)**: Databricks CLI 1.16.1,
installed via `winget install Databricks.DatabricksCLI`, standalone binary,
added to User PATH. Not referenced in `pyproject.toml` — this is
operator/dev tooling, the same category as Git, not a runtime dependency.

No new local (`uv`-managed) dependencies introduced in Milestone 13.

## Databricks Status
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`, `models`,
  `inference`, `monitoring`
- Model registry: unchanged from Milestone 12 (`logistic_regression_detector`
  v1 `champion`, v2 `archived`)
- **New this milestone**: secret scope `ced-secrets` (created, validated,
  currently unused by any pipeline); service principal `test_sp` (created,
  scoped, currently unused by any pipeline); `system.access.audit`
  confirmed populated
- Notebook execution: unchanged — orchestrated via Airflow for both DAGs,
  manual "Run All" available for ad hoc/debugging use

## Airflow Status
Unchanged from Milestone 12. Fernet key confirmed present this milestone
(light-touch check only, per user direction — no deeper investigation of
Airflow's own security posture undertaken).

## Testing Setup
- Unchanged: 34 tests. Milestone 13 introduced no new automated tests —
  this milestone's verification was manual/empirical against a live
  Databricks workspace (CLI commands, notebook cells, API calls), the same
  pattern used for Milestone 12's serverless-compute verification.

## Linting/Formatting Setup
- No changes this milestone.

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR
  to `main`.
- Unaffected by Milestone 13 — confirmed green as of Milestone 12, no code
  changed since.
- CI/CD extension (credentials in Actions, Docker build, deployment
  validation) is explicitly **Milestone 14**, not this milestone.

## Commands Used to Verify Milestone 13

Databricks CLI setup:
```powershell
winget install Databricks.DatabricksCLI
# Add install directory to User PATH, open new terminal
databricks --version
databricks configure --token
databricks auth profiles
```

Secret scope verification:
```bash
databricks secrets create-scope ced-secrets
databricks secrets list-scopes
databricks secrets put-secret ced-secrets test-key3 --string-value "hello-world"
databricks secrets list-secrets ced-secrets
```
```python
from databricks.sdk.runtime import dbutils

value = dbutils.secrets.get(scope="ced-secrets", key="test-key3")
print(f"Retrieved length: {len(value)}")  # 11
print(value)  # [REDACTED]
```

RBAC verification (SQL, run in a Databricks notebook):
```sql
SHOW GRANTS ON SCHEMA ced.training;
GRANT SELECT ON SCHEMA ced.training TO `some-placeholder-group`;  -- rejected: PRINCIPAL_DOES_NOT_EXIST
GRANT SELECT ON SCHEMA ced.training TO `vigneshram230693@gmail.com`;  -- succeeded
GRANT USE CATALOG ON CATALOG ced TO `374365a1-96f6-4597-af4c-a82aec75fff6`;
GRANT USE SCHEMA ON SCHEMA ced.training TO `374365a1-96f6-4597-af4c-a82aec75fff6`;
GRANT SELECT ON SCHEMA ced.training TO `374365a1-96f6-4597-af4c-a82aec75fff6`;
```
```bash
# ~/.databrickscfg profile [ced-training-sp] with SP client_id/client_secret
databricks current-user me --profile ced-training-sp
databricks api get /api/2.1/unity-catalog/schemas/ced.training --profile ced-training-sp  # 200 OK
databricks api get /api/2.1/unity-catalog/schemas/ced.bronze --profile ced-training-sp     # correctly denied
databricks api get /api/2.1/unity-catalog/catalogs/ced --profile ced-training-sp           # 200 OK
```

Audit log verification (SQL):
```sql
SHOW SCHEMAS IN system;
SHOW TABLES IN system.access;
SELECT * FROM system.access.audit LIMIT 5;
```

`uv run ruff check .` and `uv run ruff format --check .` not re-run this
milestone — no project code changed.