# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 15_

_Milestone 15 status: 📐 DESIGNED ONLY, NOT BUILT, NOT DEPLOYED — Docker
adoption scoped specifically against Databricks Container Services (DCS),
targeting the training workload. A `Dockerfile` extending
`databricksruntime/standard:17.3-LTS`, pinned with the exact package
versions read from the live training notebook (`mlflow-skinny==3.8.1`,
`pandas==2.2.3`, `scikit-learn==1.6.1`, `xgboost==3.4.1`), and
`training/train_model_job.py` (a script-task adaptation of the real,
verified `notebooks/train_model.py`, with exactly two changes — see
ADR-020) were written but never built or run. `docker build` was never
successfully executed — Docker Desktop on the dev machine became unusably
slow and hung the machine; this was not resolved and was deliberately left
unfixed rather than blocking the milestone's close. An annotated Databricks
Jobs API payload (`scripts/dcs_job_spec.json`) was written with every
placeholder and unverified assumption called out explicitly. DCS deployment
itself was never in scope for this milestone by deliberate choice — a
14-day free trial workspace with classic compute was considered and
explicitly declined in favor of keeping this a documented design exercise.
See ADR-020 for full reasoning, options considered, and consequences. No
pipeline/notebook code changed — `notebooks/train_model.py` and the live
Airflow-orchestrated training path are completely unaffected by this
milestone's work; `training/train_model_job.py` is a new, parallel,
undeployed file, not a replacement._

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

**Milestone 15 — Docker / Databricks Container Services (training workload)**

- **`docker/train-job/Dockerfile`** — written, never built. Extends
  `databricksruntime/standard:17.3-LTS` (current LTS as of Sept 2026, chosen
  as the nearest reasonable equivalent to the live pipeline's serverless
  environment version 5 — no official mapping exists between the two
  versioning schemes, flagged explicitly in the file). Pins
  `mlflow-skinny==3.8.1`, `pandas==2.2.3`, `scikit-learn==1.6.1`,
  `xgboost==3.4.1` — read directly from `%pip freeze` against the live
  training notebook, not invented. Does not reinstall `pyspark` (ships with
  the base image).
- **`docker/train-job/README.md`** — documents purpose, exact
  build/smoke-test commands, and the full unverified-status table. Also
  notes a possible unblocking path (Docker Engine directly in the existing
  WSL2 distro, bypassing Docker Desktop) for future reference — not
  pursued; user chose to leave the Docker Desktop problem unresolved.
- **`training/train_model_job.py`** — script-task adaptation of the real
  `notebooks/train_model.py`. Two changes from the source: removed the
  `%pip install xgboost` + `dbutils.library.restartPython()` cell (obsoleted
  by the image baking xgboost in at build time), and replaced the
  notebook-specific `databricks.sdk.runtime` import of `spark` with
  `SparkSession.builder.getOrCreate()` (documented pattern for non-notebook
  Databricks Job script tasks). Everything else — feature columns, the
  in-memory join and its ADR-014 row-count assertion, the stratified split,
  the baseline reference run, both training runs, registered model names —
  is unchanged from the verified M8 source.
- **`scripts/dcs_job_spec.json`** — annotated Databricks Jobs API payload
  (new-cluster `docker_image` block, `SINGLE_USER` access mode,
  `spark_python_task`). Every placeholder (registry URL, workspace path,
  node type, running identity) and every unverified assumption (chiefly:
  whether `SINGLE_USER` + `docker_image` + Unity Catalog combine cleanly on
  real DCS compute) is called out inline via `_*_note` keys, and the file is
  explicitly annotated as non-submittable in its current form (those keys
  must be stripped before it would be a valid API payload).
- **New `docs/adr/ADR-020-docker-container-services.md`** — full options
  considered (client-side container vs. free-trial verified deployment vs.
  designed-only DCS path — the last one chosen), rationale, and
  consequences, including an explicit statement that this partially, not
  fully, closes the Docker gap in the target resume statement.
- **Blocker, deliberately left unresolved:** Docker Desktop on the dev
  machine could not be kept running reliably (severe slowdowns / hangs the
  machine). User explicitly chose not to fix this before closing the
  milestone.
- **Nothing in this milestone changed the live, working pipeline.** The
  real Airflow-orchestrated training path still runs
  `notebooks/train_model.py` as a notebook on serverless compute, exactly
  as verified in M8.

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
  Milestone 14 (delivered) and unaffected further by Milestone 15.

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
- Actually building and smoke-testing the M15 Docker image locally —
  blocked by Docker Desktop performance, not by architecture; a Docker
  Engine-in-WSL2 alternative was identified but not pursued.
- Actually submitting `scripts/dcs_job_spec.json` against a real
  classic-compute Databricks workspace (trial or paid), to move any part
  of M15 from DESIGNED to IMPLEMENTED & VERIFIED.
- Milestone 16 and remaining milestones per the approved roadmap — not
  yet scoped in detail.

---

## Current Work
None in progress. Milestone 15 is closed.

## Pending Work
Milestone 16 next, per the approved roadmap — not yet scoped in detail.
Milestones 16–23 not yet scoped in detail — do not begin without explicit
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
| CI extended with `dag-integrity` (Airflow installed only in that CI job, never a project dependency) and `databricks-smoke-test` (read-only, authenticated as `test_sp`, push-to-`main`-only trigger to protect secrets from PR-triggered runs); personal-PAT-based smoke test and full deploy automation both explicitly considered and rejected | **ADR-019** (Milestone 14) |
| Docker adoption scoped to Databricks Container Services (DCS) for the training workload specifically, as a designed-only learning exercise; a client-side container (generator/CI script) and a real trial-workspace deployment were both considered and explicitly declined; the image was never built (Docker Desktop performance blocker, left unresolved) | **ADR-020** (new, Milestone 15) |
| `uv` over Poetry/pip; `ruff` for lint + format | Recorded here only |

---

## Known Issues
- `ced.inference.detection_results`'s persisted feature columns are raw,
  not imputed — Technical Debt #28. Unaffected by Milestone 15.
- Monitoring's `run_id` is a fresh UUID per run — Technical Debt #29.
  Unaffected by Milestone 15.
- PAT lifecycle still has no monitoring. Unchanged from Milestone 13 — the
  `databricks-smoke-test` job authenticates as `test_sp` via OAuth, not
  the personal PAT, so it does not address this gap. See ADR-007 Future
  Considerations.
- **`test_sp` now has an automated consumer (the CI smoke test), but is
  still not adopted into the training pipeline itself.** Unchanged since
  Milestone 14 — `train_model.py` / `validate_and_promote_model.py` still
  run under the personal account, not as `test_sp`, and M15's
  `training/train_model_job.py` (also unadopted, also unbuilt) doesn't
  change this either. See ADR-007 / ADR-019 Future Considerations.
- **`system.access.audit` is verified and populated but nothing consumes
  it yet.** No dashboard or scheduled query exists. Unaffected by
  Milestone 15.
- Local reproduction of the `dag-integrity` CI job requires explicitly
  invoking `python3.12`, not the WSL2 distro's bare `python3` (which
  resolves to 3.14). Unaffected by Milestone 15.
- **NEW — Docker Desktop on the dev machine is effectively unusable**
  (severe slowdowns / hangs the machine). Blocks even local-only
  verification of the M15 Docker artifacts. A lighter-weight alternative
  (Docker Engine directly inside the existing WSL2 distro, no Docker
  Desktop GUI) was identified as a candidate fix but not attempted this
  milestone; user explicitly chose to leave this unresolved.
- **NEW — `docker/train-job/Dockerfile` and `training/train_model_job.py`
  are entirely unverified.** Not built, not run, not deployed. See ADR-020.
  `training/train_model_job.py` has one specific unverified assumption
  worth tracking: whether `SparkSession.builder.getOrCreate()` behaves as
  expected when run as a real Databricks Job `spark_python_task` (vs. the
  notebook-context `databricks.sdk.runtime` pattern the verified
  `train_model.py` actually uses).
- **NEW — `scripts/dcs_job_spec.json`'s base-image runtime tag
  (`17.3-LTS`) is an assumption, not a verified match** for the live
  pipeline's serverless environment version 5 — no official mapping exists
  between classic Databricks Runtime versions and serverless environment
  versions. See ADR-020 and the Dockerfile header.

## Technical Debt
1–19. Unchanged from Milestone 8 — see prior version of this file / git
history.

~~20. Champion/challenger comparison branch unverified against live
output.~~ **RESOLVED at Milestone 12.**

21–29. Unchanged from Milestone 12 — see prior version of this file.
None resolved or newly introduced by Milestone 13, 14, or 15 (Milestone 15
concerned an unbuilt, undeployed design artifact, not pipeline code).

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
| GitHub Actions CI | 3 jobs (`lint-and-test`, `dag-integrity`, `databricks-smoke-test`); 3 repo secrets (`DATABRICKS_HOST`, `DATABRICKS_SP_CLIENT_ID`, `DATABRICKS_SP_CLIENT_SECRET`) | ✅ Verified (Milestone 14) — including a deliberate negative test (invalid secret correctly fails the job); unaffected by Milestone 15 |
| `system.access.audit` | Populated, regional, 365-day retention (per Databricks documentation) | ✅ Verified (Milestone 13) |
| Unity Catalog model registry | `ced.models.logistic_regression_detector`: v1 → `champion`, v2 → `archived`; `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified (unchanged) |
| Docker Desktop | Installed, but became unusably slow / hung the machine | ❌ Not functional (Milestone 15) — left unresolved by user's explicit choice |
| Docker image `ced-train-job` | Dockerfile written, never built | 📐 Designed only (Milestone 15) — see ADR-020 |
| Databricks Container Services | Not enabled on any workspace; no classic/dedicated compute available on Free Edition | 📐 Designed only (Milestone 15) — never attempted |

## Repository Structure (as of Milestone 15)
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
│ │ ├── ADR-019-cicd-extension.md
│ │ └── ADR-020-docker-container-services.md (new, Milestone 15)
│ ├── security/ (empty — consider moving ADR-007 detail here in future)
│ ├── governance/ (empty)
│ ├── mlops/ (empty)
│ └── nfr/ (empty)
├── data_generation/
├── ingestion/
├── training/
│ ├── train_model_job.py (new, Milestone 15 — designed only, never run)
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
│ └── tests/
│   └── test_dag_integrity.py
├── scripts/
│ ├── ci_databricks_smoke_test.py
│ └── dcs_job_spec.json (new, Milestone 15 — designed only, not submittable as-is)
├── tests/
├── docker/
│ └── train-job/ (new, Milestone 15 — designed only, never built)
│   ├── Dockerfile
│   └── README.md
└── .github/workflows/ci.yml (unchanged since Milestone 14 — 3 jobs)
```

Files added this milestone: `docker/train-job/Dockerfile`,
`docker/train-job/README.md`, `training/train_model_job.py`,
`scripts/dcs_job_spec.json`, `docs/adr/ADR-020-*.md`, plus this updated
status document and `docs/current-context.md`. No `pyproject.toml` change —
none of this milestone's artifacts are Python-project dependencies (the
Docker image, had it been built, would carry its own pinned dependencies
independently of `uv`). `.github/workflows/ci.yml` is unchanged — this
milestone did not touch CI.

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
Docker Desktop is installed but non-functional (Milestone 15) — also not a
project dependency in `pyproject.toml`, same category.

No new local (`uv`-managed) dependencies introduced in Milestone 13, 14, or
15.

## Databricks Status
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`, `models`,
  `inference`, `monitoring`
- Model registry: unchanged from Milestone 12 (`logistic_regression_detector`
  v1 `champion`, v2 `archived`)
- Secret scope `ced-secrets` (created, validated, currently unused by any
  pipeline); service principal `test_sp` (created, scoped, now has an
  automated CI consumer as of M14, still unused by the training pipeline
  itself); `system.access.audit` confirmed populated
- **Databricks Container Services**: not enabled on any workspace this
  project has access to. No classic/dedicated compute available on Free
  Edition. Designed against only, per ADR-020 (Milestone 15)
- Notebook execution: unchanged — orchestrated via Airflow for both DAGs,
  manual "Run All" available for ad hoc/debugging use

## Airflow Status
Unchanged from Milestone 12. Fernet key confirmed present (Milestone 13,
light-touch check only, per user direction — no deeper investigation of
Airflow's own security posture undertaken). Unaffected by Milestone 15.

## Testing Setup
- 34 tests under `tests/`, run by the `lint-and-test` CI job (unchanged
  since Milestone 13).
- 5 tests under `airflow/tests/` (`test_dag_integrity.py`), run by the
  separate `dag-integrity` CI job in its own Airflow-installed environment
  (Milestone 14), deliberately not counted alongside the 34 above.
- The `databricks-smoke-test` job (Milestone 14) is not a pytest suite —
  it's a single pass/fail script (`scripts/ci_databricks_smoke_test.py`)
  checking live credential/grant validity, on every push to `main`.
- **No new tests this milestone.** `training/train_model_job.py` has no
  test coverage — it has never been run, so there is nothing to assert
  against yet. If M15's design is ever actually built and run, adding
  tests for it becomes meaningful; writing them against unexecuted code
  now would be testing an assumption, not a behavior.

## Linting/Formatting Setup
- No changes this milestone.

## CI/CD Status
- GitHub Actions workflow `ci.yml`, three jobs, unchanged since Milestone
  14:
  - `lint-and-test`: lint → format check → test, on push/PR to `main`.
  - `dag-integrity`: parses both Airflow DAGs via `DagBag` in an isolated
    environment, on push/PR to `main`.
  - `databricks-smoke-test`: read-only live-workspace check authenticated
    as `test_sp`, on push to `main` only.
- All three still confirmed green as of Milestone 14; **not re-run or
  re-verified this milestone**, since no CI-relevant code changed.
- Docker build and deployment validation remain out of CI scope — M15's
  Docker artifacts were never built even locally, so there is nothing
  ready to add to CI, and doing so was never in scope for this milestone
  regardless (see ADR-020, and ADR-019's original reasoning for why a
  Docker CI stage needs genuine purpose before being added).

## Commands Used to Verify Milestone 15

**None.** This is a deliberate departure from every prior milestone's
verification discipline, and is called out explicitly rather than omitted:
`docker build` was attempted by the user but never completed successfully —
Docker Desktop on the dev machine became unusably slow and hung the
machine. No further commands were run. The user explicitly chose to leave
this unresolved rather than continue troubleshooting Docker Desktop or
pursue the lighter-weight Docker-Engine-in-WSL2 alternative that was
identified as a possible fix. Every artifact produced this milestone
(`docker/train-job/Dockerfile`, `docker/train-job/README.md`,
`training/train_model_job.py`, `scripts/dcs_job_spec.json`) is therefore
unverified by any command output, and is documented as such throughout this
file and in ADR-020.

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