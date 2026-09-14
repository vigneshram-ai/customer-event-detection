# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 12_

_Milestone 12 status: IMPLEMENTED AND VERIFIED — real Airflow orchestration
replaces the temporary smoke-test DAG. Two independently-triggered DAGs:
`ced_inference_pipeline` (Bronze→Silver→Gold→batch inference→monitoring) and
`ced_training_pipeline` (train→validate/promote), connected only through the
Unity Catalog model registry `champion` alias, not through Airflow
dependencies. Both DAGs run via `DatabricksSubmitRunOperator` using the
multi-task `tasks=[...]` shape, required for Databricks Free Edition
serverless compute — `DatabricksNotebookOperator` does not support
serverless in the installed provider version. Both DAGs ran end-to-end
successfully with verified (not just "ran without error") output. See
ADR-002 and ADR-018 for full design detail, including a documented
environment change: Airflow now runs natively inside WSL2 Ubuntu, not
Docker Compose, reversing the "Windows native, no WSL2" principle stated
since Milestone 1._

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified

**Milestones 1–11** — unchanged from prior status; see git history / earlier
versions of this file for full detail.

**Milestone 12 — Real Airflow orchestration**
- **Environment change, documented not silently patched**: the Milestone 1
  Docker Compose Airflow setup could not run on this laptop (Docker Desktop's
  own overhead exhausted resources before Airflow's containers were even
  healthy). Airflow does not support native Windows Python installation
  either (a hard platform check, not a config issue). Resolution: Airflow
  3.3.1 now runs natively inside a dedicated WSL2 Ubuntu distro (Python 3.12
  venv, `airflow standalone`, SQLite metadata DB, `SequentialExecutor`),
  `dags_folder` pointed at the Windows-mounted project path. This reverses
  the "Windows native, no WSL2 terminal use" principle stated since
  Milestone 1 — see ADR-018.
- **`apache-airflow-providers-databricks` 7.18.1** installed into the WSL2
  Airflow venv (not the project's `uv` environment — no `pyproject.toml`
  change). `databricks_default` connection configured via the Airflow UI
  using the existing workspace PAT.
- **Serverless compute compatibility — empirically resolved, not assumed**:
  `DatabricksNotebookOperator` requires a cluster reference (confirmed via
  a 400 API error) and does not support Free Edition serverless in the
  installed provider version (a brief upstream serverless-support PR was
  reverted before this version). The legacy `DatabricksSubmitRunOperator`
  single-task shorthand (`notebook_task=`) also fails, for the same reason.
  **Working pattern**: `DatabricksSubmitRunOperator` with the multi-task
  `tasks=[...]` array (task-spec dicts, no cluster field), confirmed via a
  minimal single-task test DAG before building the full pipelines. See
  ADR-018 for full detail.
- **`ced_inference_pipeline`** (`airflow/dags/ced_inference_pipeline.py`) —
  5 tasks, linear dependency chain: `bronze_ingestion >>
  silver_transformation >> gold_feature_engineering >> batch_inference >>
  monitoring`. `schedule=None` (manual trigger only — WSL2 Airflow has no
  persistent scheduler surviving a laptop restart, so a cron schedule would
  silently never fire). `retries=1`, `retry_delay=2min` per task. Each task
  is its own `DatabricksSubmitRunOperator` (not bundled into one multi-task
  call) for independent retry/failure visibility per stage.
  - **Full run verified**: all five tasks succeeded. Fresh timestamps
    confirmed in `ced.bronze`, `ced.gold.customer_events_features`, and
    `ced.inference.detection_results`. `ced.monitoring.batch_quality_report`
    grew from 158 to 237 rows (+79, matching exactly one clean monitoring
    run with a new `run_id` — no double-write). Silver `_rejects` tables
    confirmed at 0.
- **`ced_training_pipeline`** (`airflow/dags/ced_training_pipeline.py`) —
  2 tasks: `train_model >> validate_and_promote_model`. Deliberately **not**
  chained to `ced_inference_pipeline` — connected only via the Unity Catalog
  `champion` alias, which `ced_inference_pipeline` always reads at run time.
  `schedule=None` (manual trigger only, same reasoning as above). Assumes
  Gold is already current; does not re-run Bronze/Silver/Gold itself.
  - **Full run verified — and the first live execution of the
    champion/challenger comparison branch** (previously Technical Debt #20,
    unverified since Milestone 9): v2 trained, passed all three validation
    gate thresholds (`recall_channel_deviation` 1.0, `recall` 1.0,
    `precision` 0.9879), tagged `challenger`. F1 comparison against
    champion v1 was an exact tie (0.9939 vs. 0.9939) — the documented
    tie-break rule ("ties favor the incumbent champion," ADR-015) correctly
    held v1 as `champion`, tagged v2 `archived`. **Technical Debt #20 is
    resolved**: the comparison logic is confirmed correct under a real tie,
    not just confirmed to execute.
- **Baseline detector (`baseline_detector.py`) deliberately excluded** from
  both DAGs — it's a one-time analytical comparison (Milestone 7), not part
  of the production inference path.
- **Temporary test/smoke DAGs retired**: `00_environment_smoke_test.py`
  (served its Milestone 1 purpose) and `99_databricks_serverless_test.py`
  (its verification purpose is now fully captured in ADR-018) both deleted
  after the real DAGs were verified working.
- **New ADRs**: ADR-002 ("Airflow as the Orchestration Layer" — pending
  since Milestone 1, now formally written with real content) and ADR-018
  ("Milestone 12 — Real Orchestration": two-DAG split rationale, WSL2
  environment change, serverless compute compatibility finding).
- **CI confirmed green** — no `pyproject.toml` changes, no new local
  dependencies (Databricks provider lives only in the WSL2 Airflow venv).

### 🟡 Implemented, Not Fully Verified
- None currently — Milestone 12 resolved the prior open item (champion/
  challenger comparison branch, Technical Debt #20).
- **`batch_inference.py`'s exact resolved `model_version` string** —
  inferred, not directly observed (Technical Debt #26). Unaffected by
  Milestone 12.

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale — **now written**, see ADR-002
  (moved out of this section).
- Time-of-day deviation feature.
- `ced.training` schema access restricted to a training-job identity — cannot be
  enforced on Free Edition (single-user).
- Live/shadow evaluation for the champion/challenger pattern.
- A genuinely new/unseen event batch for inference — still the same sample-
  based batch from Milestone 10; Milestone 12's orchestration runs the same
  notebook, doesn't change its data source.
- Distributed (`spark_udf`-based) batch scoring and a custom `PythonModel`-based
  flavor-agnostic probability output.
- A real (cron-based) Airflow schedule — deliberately deferred; the current
  WSL2-native Airflow instance has no persistent scheduler surviving a
  laptop shutdown, so a configured schedule would be non-functional in
  practice. Both DAGs use `schedule=None` (manual trigger) as an explicit,
  reasoned decision, not a placeholder — see ADR-002/ADR-018.
- Deterministic `run_id` generation for monitoring (to make retries
  idempotent) — flagged as a real gap in ADR-018, not yet implemented since
  both DAGs are manually triggered and the practical risk is currently low.
- Evidently Test Suites wired to actual pipeline gating (e.g., failing a
  DAG task on `DriftedColumnsCount` share exceeding a threshold) — still
  not implemented; Milestone 12 provides the orchestration substrate this
  would need, but gating itself remains a documented future extension.
- PySpark-native (distributed) drift/quality computation for larger-than-driver-
  memory datasets — unchanged, still a documented scaling consideration only.

### ⏳ Future
- Verifying batch inference's exact `model_version` output string directly
  (Technical Debt #26).
- A genuinely new event batch for batch inference.
- Append/dedup strategy for `ced.inference.detection_results` (Technical
  Debt #24) — orchestration doesn't resolve this; still `overwrite` mode.
- Re-running monitoring against a genuinely new (non-overlapping) batch,
  once one exists, to get a real drift comparison rather than a negative
  control.
- Milestone 13 onward per the approved roadmap: security, full CI/CD
  extension, and remaining milestones.

---

## Current Work
None in progress. Milestone 12 is closed.

## Pending Work
Milestones 13–23 per the approved roadmap. Next milestone not yet scoped in
detail — do not begin without explicit user confirmation.

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
| Monitoring uses Evidently directly (no hand-rolled statistics); auto-selected drift tests (not forced PSI); Milestone 10's batch treated as current-under-monitoring with explicit negative-control framing; reference/current imputation parity applied independently of the (corrected) upstream gap; extraction verified against Evidently's real `report.dict()` schema | **ADR-017** |
| Airflow selected as orchestration layer over no-orchestrator and Databricks Workflows alternatives | **ADR-002** (new, Milestone 12) |
| Two-DAG split (inference vs. training), decoupled via the `champion` alias not Airflow dependencies; WSL2-native execution environment (reversing "Windows native, no WSL2"); `DatabricksSubmitRunOperator` + multi-task `tasks=[...]` shape required for Free Edition serverless compute | **ADR-018** (new, Milestone 12) |
| `uv` over Poetry/pip; `ruff` for lint + format | Recorded here only |

---

## Known Issues
- None blocking. CI confirmed green through Milestone 12.
- `ced.inference.detection_results`'s persisted feature columns are raw, not
  imputed — see Technical Debt #28. Does not affect `detection_score`/
  `detection_flag`, which are correct. Unaffected by Milestone 12.
- Monitoring's `run_id` is a fresh UUID per run, not derived deterministically
  from Airflow's run context — a retried task after partial failure could in
  principle double-write a batch. Low practical risk currently (manual
  trigger only); see ADR-018 Future Considerations.

## Technical Debt
1–19. Unchanged from Milestone 8 — see prior version of this file / git history.

~~20. Champion/challenger comparison branch unverified against live output.~~
**RESOLVED at Milestone 12** — verified via `ced_training_pipeline`'s first
real run: v2 passed the gate, tied champion v1 on F1, tie-break rule
correctly held v1 as champion. See ADR-018.

21. `archived` alias only tags the single most-recently-losing version.
22. Milestone 10's batch inference scores a reproducible sample of existing Gold
    data, not genuinely new/unseen events. Still the reason Milestone 11's
    near-zero-drift result must be read as a negative control — unaffected
    by Milestone 12's orchestration (same underlying notebook, same data
    source).
23. `predict_proba` obtained via sklearn-specific unwrap, not flavor-agnostic.
24. `ced.inference.detection_results` uses `mode("overwrite")`, no historical
    accumulation. Not addressed by adding orchestration.
25. `fillna(0)` on amount-based Gold features collapses two distinct NULL causes.
26. Milestone 10's exact `model_version` output string was inferred, not
    directly observed.
27. Monitoring's Evidently-output extraction (`flatten_evidently_report`)
    depends on Evidently's internal `report.dict()` schema, not a documented
    stable public contract.
28. `ced.inference.detection_results`'s persisted `FEATURE_COLUMNS` are
    raw (non-imputed) Gold values, not the values actually fed to the model.
    See Milestone 11 detail above (unchanged this milestone).
29. **NEW — Monitoring's `run_id` is a fresh UUID per run**, not derived
    deterministically from the Airflow run context. A task-level retry after
    a partial failure (write succeeds, task errors before confirming) could
    double-write a batch under a new `run_id`. Low risk currently since both
    DAGs are manually triggered, not scheduled. See ADR-018.

---

## Environment / Setup Information

| Item | Value | Verification status |
|---|---|---|
| OS | Windows, with WSL2 Ubuntu used for Airflow only (reversing the prior "no WSL2 terminal use" principle — see ADR-018) | ✅ Verified |
| Project Python (via `uv`) | 3.11.16 | ✅ Verified (unchanged, project code remains Windows-native) |
| Airflow Python (WSL2 venv) | 3.12.13 | ✅ Verified |
| `uv` version | 0.12.5 | Stated by user |
| Docker Desktop | No longer used for Airflow (resource constraints on this laptop); still used as WSL2's own backend distro (`docker-desktop`), separate from the `Ubuntu` distro running Airflow | ✅ Verified (environment change, Milestone 12) |
| Airflow | 3.3.1, native in WSL2 Ubuntu, `airflow standalone` (SQLite, `SequentialExecutor`), manually started per session | ✅ Verified |
| `apache-airflow-providers-databricks` | 7.18.1 | ✅ Verified |
| Git | `main` branch, GitHub remote connected, 2.55.0.windows.4 | ✅ Verified |
| Databricks workspace | Free Edition, `https://dbc-01205ae9-f87b.cloud.databricks.com/`, serverless compute only | ✅ Verified |
| Unity Catalog catalog | `ced` | ✅ Verified |
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold`, `ced.training`, `ced.models`, `ced.inference`, `ced.monitoring` | ✅ Verified |
| Unity Catalog model registry | `ced.models.logistic_regression_detector`: v1 → `champion`, v2 → `archived` (Milestone 12 champion/challenger tie, v1 held); `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified |
| `ced.inference.detection_results` | 500 rows, feature columns raw not imputed (Technical Debt #28); fresh timestamps confirmed post-Milestone-12 run | ✅ Verified (with caveat) |
| `ced.monitoring.batch_quality_report` | 237 rows (2 pre-M12 runs × 79 + 1 orchestrated run × 79) | ✅ Verified |

## Repository Structure (as of Milestone 12)
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
│ │ ├── ADR-002-airflow-orchestration-layer.md (new, Milestone 12)
│ │ ├── ADR-009 … ADR-017 (unchanged)
│ │ └── ADR-018-milestone-12-orchestration.md (new, Milestone 12)
│ ├── security/ (empty)
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
│   ├── ced_inference_pipeline.py (new, Milestone 12)
│   └── ced_training_pipeline.py (new, Milestone 12)
├── tests/
├── docker/ (empty — Docker no longer used for Airflow, see ADR-018)
└── .github/workflows/ci.yml
```

Note: `00_environment_smoke_test.py` and `99_databricks_serverless_test.py`
have been deleted — both served their purpose and are fully documented in
ADR-018 if ever needed for reference.

## Installed Dependencies

**Production**: `databricks-sdk>=0.133.0`, `python-dotenv>=1.2.3`, `pandas`.
Databricks-side only (not `pyproject.toml` dependencies): `xgboost`, `mlflow`,
`evidently`.

**Dev**: `pytest>=8.3.0`, `ruff>=0.6.0`.

**Airflow (WSL2 venv only, not `pyproject.toml`)**: `apache-airflow==3.3.1`,
`apache-airflow-providers-databricks==7.18.1`.

No new local (`uv`-managed) dependencies introduced in Milestone 12.

## Databricks Status
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`, `models`,
  `inference`, `monitoring`
- `ced.monitoring.batch_quality_report` — 237 rows total (79 added by the
  Milestone 12 orchestrated run)
- Model registry: `logistic_regression_detector` v1 remains `champion`; v2
  (trained via `ced_training_pipeline`) tagged `archived` after tying v1 on
  F1 and losing the incumbent tie-break
- Notebook execution: now orchestrated via Airflow for both DAGs; manual
  "Run All" remains available for ad hoc/debugging use

## Airflow Status
- **3.3.1, running natively in WSL2 Ubuntu** (not Docker Compose — see
  ADR-018 for the environment change and rationale)
- `apache-airflow-providers-databricks` 7.18.1 installed; `databricks_default`
  connection configured
- `dags_folder` points at the Windows-mounted project path — DAG files are
  version-controlled in the main repo, no separate copy step
- Two DAGs: `ced_inference_pipeline` (5 tasks, verified end-to-end) and
  `ced_training_pipeline` (2 tasks, verified end-to-end, including the
  champion/challenger tie-break)
- Both DAGs: `schedule=None` (manual trigger only — no persistent scheduler
  survives a laptop shutdown on this setup)
- No longer running: Docker Compose Airflow stack, smoke-test DAG,
  serverless-test DAG (all retired this milestone)

## Testing Setup
- Unchanged: 34 tests, no automated coverage for Databricks/Spark-only
  notebooks or Airflow DAGs (consistent pattern — orchestration logic is
  tested via live execution against Databricks, not local unit tests).

## Linting/Formatting Setup
- No new lint/format exceptions required. DAG files live under `airflow/dags/`,
  outside the `uv`/`ruff`-managed project scope (Airflow's own Python
  environment is separate — see WSL2 venv note above).

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to
  `main`.
- ✅ Confirmed green on `main` through Milestone 12 (per user confirmation).
- Still does not build/run Docker, Airflow, or touch Databricks (by design).

## Commands Used to Verify Milestone 12
Airflow standalone startup (WSL2 shell):
```bash
cd ~/airflow-standalone
source venv/bin/activate
export AIRFLOW_HOME=~/airflow-standalone/airflow_home
airflow standalone
```

Both DAGs triggered manually via the Airflow UI (`http://localhost:8080`).

Verification queries run against Databricks to confirm `ced_inference_pipeline`
did real work (not just "ran without error"): fresh timestamps in
`ced.bronze`/`ced.gold.customer_events_features`/`ced.inference.detection_results`;
row count on `ced.monitoring.batch_quality_report` (237, up from 158);
`_rejects` table counts (0) in Silver.

`ced_training_pipeline` output (condensed, from live task logs):
```text
train_model completed successfully.
validate_and_promote_model completed successfully.

Evaluating ced.models.logistic_regression_detector v2
  [PASS] recall_channel_deviation: 1.0000 (threshold >= 0.95)
  [PASS] recall: 1.0000 (threshold >= 0.95)
  [PASS] precision: 0.9879 (threshold >= 0.9)
v2 tagged 'challenger' (gate passed).
Comparing challenger v2 (f1=0.9939) vs. champion v1 (f1=0.9939)
CHAMPION HOLDS — v1 outperforms or ties v2 on f1.
v2 tagged 'archived'.

Final registered aliases:
  archived -> v2
  champion -> v1
```

`uv run ruff check .` and `uv run ruff format --check .` run locally to
confirm lint/format unaffected; CI confirmed green.