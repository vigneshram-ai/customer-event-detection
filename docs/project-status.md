# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 14_

_Milestone 14 status: IMPLEMENTED AND VERIFIED — CI/CD extended with two
new GitHub Actions jobs: `dag-integrity` (parses both Airflow DAGs with
`DagBag` in an isolated environment, installed only for this job — Airflow
remains excluded from `pyproject.toml`, consistent with ADR-018) and
`databricks-smoke-test` (authenticates as the `test_sp` service principal
created in Milestone 13 via OAuth M2M and performs read-only checks
against `ced` / `ced.training`, restricted to `push` on `main` only — never
`pull_request` — so live-workspace secrets are never exposed to PR-triggered
runs, including from forks). Both jobs verified passing against the real
GitHub Actions environment and the real live workspace; a deliberate
negative test (temporarily invalid `test_sp` secret) confirmed the smoke
test fails correctly rather than passing silently. `test_sp`, unused since
Milestone 13, now has a genuine automated consumer. No pipeline/notebook
code changed this milestone. See ADR-019 for full detail._

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
"verify before building" discipline. See ADR-007 for full detail._

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

**Milestone 14 — CI/CD extension (DAG integrity + live smoke test)**

- **New `dag-integrity` CI job.** Installs `apache-airflow==3.3.1` +
  `apache-airflow-providers-databricks==7.18.1` (pinned to match the real
  WSL2 versions, via Airflow's official constraints file) into a
  throwaway environment isolated from the main `uv`-managed project deps.
  Runs `airflow/tests/test_dag_integrity.py`: asserts zero `DagBag`
  import errors, the expected DAG IDs, the expected task ID order for
  both DAGs, that both remain unscheduled (`NullTimetable`, confirming
  `schedule=None` per ADR-018), and that retries are configured. Verified
  locally (5/5 passing against the real DAGs) and in GitHub Actions.
- **New `databricks-smoke-test` CI job.** Authenticates as `test_sp`
  (Milestone 13's service principal) via OAuth M2M, using GitHub Actions
  secrets `DATABRICKS_HOST` / `DATABRICKS_SP_CLIENT_ID` /
  `DATABRICKS_SP_CLIENT_SECRET`. Performs two read-only checks: reading
  catalog `ced` and reading schema `ced.training` — the exact grant chain
  manually verified in Milestone 13, now automated. **Runs only on `push`
  to `main`, never on `pull_request`** — a deliberate trust-boundary
  decision so PR-triggered workflows (including from forks, on a public
  repo) never get access to live-workspace secrets.
- **Verified end-to-end against the real environment**: pushed to
  GitHub, confirmed `databricks-smoke-test` does not appear at all in a
  PR's checks (trigger scoping confirmed), confirmed all three jobs pass
  on `main`, and ran a deliberate negative test — temporarily invalidating
  the `test_sp` GitHub secret — which correctly failed the smoke test
  rather than passing silently, then restored to green.
- **`test_sp` now has a genuine automated consumer** — resolves the
  Milestone 13 gap where it was created, scoped, and verified once by
  hand, then left unused. Migrating the *training pipeline itself* to run
  as `test_sp` remains separate, undone future work (ADR-007) — this
  milestone does not change that.
- **New `docs/adr/ADR-019-cicd-extension.md`** — full options considered
  (including why a personal-PAT-based smoke test and full deploy
  automation were both rejected) and rationale.
- **No pipeline, DAG, or notebook code changed.** `airflow/dags/*.py` and
  all `notebooks/*.py` files are unmodified — this milestone extended
  what CI *verifies*, not what the pipeline *does*.
- **Environment note surfaced during verification**: the WSL2 distro's
  bare `python3` resolves to 3.14 by default, distinct from the 3.12.13
  interpreter the real Airflow venv uses; local verification of the
  `dag-integrity` job requires explicitly invoking `python3.12` (and
  installing `python3.12-venv` via `apt`) rather than relying on the
  `python3` default. Not a pipeline issue — Airflow itself continues to
  run on the correct 3.12.13 venv — but worth flagging for anyone
  reproducing the local verification steps.

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
None in progress. Milestone 14 is closed.

## Pending Work
Milestone 15 next, per the approved roadmap — not yet scoped in detail.
Milestones 15–23 not yet scoped in detail — do not begin without explicit
user confirmation.

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
| PAT remains in `.env`/Airflow connection store rather than a Databricks secret scope, due to a bootstrap-circularity constraint; Unity Catalog RBAC (including service-principal identity) empirically confirmed functional on Free Edition, overturning the prior single-user assumption; `system.access.audit` confirmed populated and usable | **ADR-007** (Milestone 13) |
| CI extended with `dag-integrity` (Airflow installed only in that CI job, never a project dependency) and `databricks-smoke-test` (read-only, authenticated as `test_sp`, push-to-`main`-only trigger to protect secrets from PR-triggered runs); personal-PAT-based smoke test and full deploy automation both explicitly considered and rejected | **ADR-019** (new, Milestone 14) |
| `uv` over Poetry/pip; `ruff` for lint + format | Recorded here only |

---

## Known Issues
- None blocking. All three CI jobs confirmed green as of Milestone 14.
- `ced.inference.detection_results`'s persisted feature columns are raw,
  not imputed — Technical Debt #28. Unaffected by Milestone 14.
- Monitoring's `run_id` is a fresh UUID per run — Technical Debt #29.
  Unaffected by Milestone 14.
- PAT lifecycle still has no monitoring. Unchanged from Milestone 13 — the
  `databricks-smoke-test` job authenticates as `test_sp` via OAuth, not
  the personal PAT, so it does not address this gap. See ADR-007 Future
  Considerations.
- **`test_sp` now has an automated consumer (the CI smoke test), but is
  still not adopted into the training pipeline itself.** Narrowed from
  Milestone 13's "not yet formally adopted or deleted" — it is no longer
  purely unused infrastructure, but `train_model.py` /
  `validate_and_promote_model.py` still run under the personal account.
  See ADR-007 / ADR-019 Future Considerations.
- **NEW — local reproduction of the `dag-integrity` CI job requires
  explicitly invoking `python3.12`, not the WSL2 distro's bare `python3`
  (which resolves to 3.14).** Discovered during Milestone 14 verification;
  does not affect the real Airflow venv (already correctly on 3.12.13) or
  the GitHub Actions runner (which installs its own clean Python), only
  local ad hoc reproduction of that specific CI job.

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
| WSL2 default `python3` | Resolves to 3.14 — distinct from the 3.12.13 Airflow venv; `python3.12-venv` must be installed via `apt` and `python3.12` invoked explicitly for local ad hoc verification (e.g. reproducing the `dag-integrity` CI job) | ✅ Verified (Milestone 14) |
| Airflow Fernet key | Present, non-default | ✅ Verified (Milestone 13, light-touch check only) |
| `uv` version | 0.12.5 | Stated by user |
| Databricks CLI | 1.16.1, installed via `winget`, added to User PATH | ✅ Verified (Milestone 13) |
| Databricks CLI auth profile | `DEFAULT`, token-based, `Valid: YES` (after PAT rotation) | ✅ Verified (Milestone 13) |
| Git | `main` branch, GitHub remote connected, 2.55.0.windows.4 | ✅ Verified |
| Databricks workspace | Free Edition, `https://dbc-01205ae9-f87b.cloud.databricks.com/`, serverless compute only | ✅ Verified |
| Unity Catalog catalog | `ced` | ✅ Verified |
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold`, `ced.training`, `ced.models`, `ced.inference`, `ced.monitoring` | ✅ Verified |
| Databricks secret scope | `ced-secrets` — created, write/read verified, notebook redaction confirmed | ✅ Verified (Milestone 13) |
| Service principal | `test_sp`, Application Id `374365a1-96f6-4597-af4c-a82aec75fff6`, OAuth client credentials generated, scoped grants on `ced` (`USE CATALOG`) and `ced.training` (`USE SCHEMA`, `SELECT`) | ✅ Verified (Milestone 13); now authenticated live from GitHub Actions as the `databricks-smoke-test` job (Milestone 14) — still not adopted into the training pipeline itself |
| GitHub Actions CI | 3 jobs (`lint-and-test`, `dag-integrity`, `databricks-smoke-test`); 3 repo secrets (`DATABRICKS_HOST`, `DATABRICKS_SP_CLIENT_ID`, `DATABRICKS_SP_CLIENT_SECRET`) | ✅ Verified (Milestone 14) — including a deliberate negative test (invalid secret correctly fails the job) |
| `system.access.audit` | Populated, regional, 365-day retention (per Databricks documentation) | ✅ Verified (Milestone 13) |
| Unity Catalog model registry | `ced.models.logistic_regression_detector`: v1 → `champion`, v2 → `archived`; `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified (unchanged) |

## Repository Structure (as of Milestone 14)
```text
customer-event-detection/
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore (includes .env)
├── .gitattributes
├── .env (gitignored, not in repo)
├── docs/
│ ├── project-status.md
│ ├── current-context.md
│ ├── architecture/ (empty)
│ ├── adr/
│ │ ├── ADR-002-airflow-orchestration-layer.md
│ │ ├── ADR-007-security-secrets-management.md
│ │ ├── ADR-009 … ADR-017 (unchanged)
│ │ ├── ADR-018-milestone-12-orchestration.md
│ │ └── ADR-019-cicd-extension.md (new, Milestone 14)
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
│ ├── dags/
│ │ ├── ced_inference_pipeline.py
│ │ └── ced_training_pipeline.py
│ └── tests/ (new, Milestone 14)
│   └── test_dag_integrity.py
├── scripts/ (new, Milestone 14)
│ └── ci_databricks_smoke_test.py
├── tests/
├── docker/ (empty — Docker no longer used for Airflow, see ADR-018)
└── .github/workflows/ci.yml (updated, Milestone 14 — 3 jobs)
```

Files added this milestone: `airflow/tests/test_dag_integrity.py`,
`scripts/ci_databricks_smoke_test.py`, `docs/adr/ADR-019-*.md`, plus the
updated `.github/workflows/ci.yml` and status/context documents. No
`pyproject.toml` change — Airflow remains excluded from project
dependencies (installed only inside the `dag-integrity` CI job's own
throwaway environment), consistent with ADR-018's treatment of Airflow as
environment-specific tooling, not a project dependency.

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
- 34 tests under `tests/`, run by the `lint-and-test` CI job (unchanged
  from Milestone 13).
- **New, Milestone 14**: 5 tests under `airflow/tests/`
  (`test_dag_integrity.py`), run by the separate `dag-integrity` CI job
  in its own Airflow-installed environment — deliberately not counted
  alongside the 34 above, since they require a different, isolated
  dependency set (see ADR-019).
- The `databricks-smoke-test` job is not a pytest suite — it's a single
  pass/fail script (`scripts/ci_databricks_smoke_test.py`) checking live
  credential/grant validity, the same style of empirical verification
  used in Milestone 13, now automated on every push to `main`.

## Linting/Formatting Setup
- No changes this milestone.

## CI/CD Status
- GitHub Actions workflow `ci.yml`, three jobs, as of Milestone 14:
  - `lint-and-test`: lint → format check → test (unchanged from prior
    milestones), on push/PR to `main`.
  - `dag-integrity` (new, M14): parses both Airflow DAGs via `DagBag` in
    an isolated environment (Airflow not a project dependency), on
    push/PR to `main`.
  - `databricks-smoke-test` (new, M14): read-only live-workspace check
    authenticated as `test_sp`, on push to `main` only.
- All three confirmed green against the real GitHub Actions environment
  and the real live Databricks workspace, including a deliberate negative
  test confirming the smoke test fails correctly on bad credentials.
- Docker build and deployment validation remain out of scope — no
  containerized component exists in the architecture yet (see ADR-019,
  "Options Considered," for why a Docker CI stage was rejected this
  milestone).

## Commands Used to Verify Milestone 14

Local `dag-integrity` reproduction (WSL2 — note explicit `python3.12`,
not bare `python3`, per the environment note above):
```bash
sudo apt install python3.12-venv
python3.12 -m venv /tmp/dagtest
/tmp/dagtest/bin/pip install "apache-airflow==3.3.1" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.1/constraints-3.12.txt"
/tmp/dagtest/bin/pip install "apache-airflow-providers-databricks==7.18.1" pytest
/tmp/dagtest/bin/python -m pytest airflow/tests -v
# Result: 5 passed
```

GitHub verification:
- Pushed a branch, opened a PR into `main` — confirmed `lint-and-test` and
  `dag-integrity` ran and passed; confirmed `databricks-smoke-test` did
  **not** appear in the PR's checks at all (trigger scoping to `push`
  confirmed working).
- Merged into `main` — confirmed all three jobs ran and passed, including
  `databricks-smoke-test` authenticating live as `test_sp`.
- Negative test: temporarily set `DATABRICKS_SP_CLIENT_SECRET` to an
  invalid value, pushed an empty commit to `main` — confirmed
  `databricks-smoke-test` failed with a clear error rather than passing
  silently. Restored the correct secret, pushed again, confirmed green.

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