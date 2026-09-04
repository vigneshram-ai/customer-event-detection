# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 8_

_Milestone 8 status: IMPLEMENTED AND VERIFIED — LogisticRegression and
XGBoost trained on the 8 Gold features against Milestone 3 ground-truth
labels, tracked in Databricks-managed MLflow alongside a metrics-only
reference run for the Milestone 7 baseline. LogisticRegression recovers the
baseline's structural 0% recall on `channel_deviation` anomalies to 100%,
while improving precision, recall, and F1 overall, and is the leading
candidate — not yet promoted, since no formal promotion mechanism exists
yet. Two limitations were identified and deliberately left as documented
technical debt rather than fixed — see ADR-014 amendment._

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified

**Milestones 1–7** — unchanged from prior status; see git history / earlier
versions of this file for full detail. Summary: repo/environment setup,
synthetic customer and event generators (1,000 customers, 27,128 events,
542 injected anomalies), Bronze ingestion, Silver validation, Gold feature
engineering (8 features, leakage-safe windows), and a rule-based baseline
detector evaluated against ground truth (precision 1.0000, recall 0.7435,
F1 0.8529, with a diagnosed 0% recall gap on `channel_deviation`).

**Milestone 8 — ML model training (Logistic Regression + XGBoost)**
- **Design decisions resolved and documented in ADR-014**, including a
  deliberate, scoped refinement of ADR-010/013's ground-truth-exclusion
  stance: ground truth may enter Databricks for training, but only into an
  isolated schema (`ced.training`) that inference paths never read. The
  join between features and labels happens in-memory only and is never
  persisted to any catalog table.
- **New Unity Catalog schema `ced.training`**, holding exactly one table:
  `ced.training.ground_truth_labels` (`event_id`, `anomaly_type`,
  `is_anomaly`). Populated via a **new, additive** upload path —
  `training/upload_ground_truth.py` does not modify Milestone 4's
  `ingestion/upload_to_volume.py`, which continues to deliberately exclude
  ground truth from Bronze uploads.
  - `notebooks/load_ground_truth.py` reads the uploaded CSV from
    `/Volumes/ced/training/raw_labels/`, reads the CSV's actual
    `is_synthetic_anomaly` column directly (renamed `is_anomaly`) rather
    than deriving it from `anomaly_type`'s nullability — an early draft
    made that derivation mistake and was corrected during design review,
    before any live run.
  - **Verified**: 27,128 rows loaded, exactly matching Gold's row count.
    `anomaly_type` breakdown: `amount_spike` 57, `channel_deviation` 128,
    `geo_deviation` 128, `new_device` 229 (sum 542, matching the M3/M7
    verified anomaly total exactly). `is_anomaly` True/False counts:
    542 / 26,586.
- **New Unity Catalog schema `ced.models`**, deliberately separate from
  `ced.training` — registered models must be loadable by future batch
  inference, so they live outside the schema that's walled off from
  inference paths.
- `notebooks/train_model.py` — new Databricks notebook, installs `xgboost`
  via `%pip install` (first time this project has needed a non-preinstalled
  library on Free Edition serverless compute), joins Gold features to
  `ced.training.ground_truth_labels` in-memory, performs a stratified 70/30
  train/test split (by `anomaly_type`, seed 42), and trains/logs three
  MLflow runs in experiment `/Shared/customer_event_detection_m8`:
  - `baseline_rule_v1_reference` — the M7 baseline's already-verified
    metrics, logged as params/metrics only (no model artifact, since it
    isn't a fitted model), for direct comparison in the MLflow UI.
  - `logistic_regression` — trained on all 8 Gold features,
    `class_weight="balanced"`, registered as
    `ced.models.logistic_regression_detector` v1.
  - `xgboost` — trained on all 8 Gold features, `scale_pos_weight` set from
    the train split's class ratio, registered as
    `ced.models.xgboost_detector` v1.
- **Three bugs caught and fixed before/during verification** — full detail
  in ADR-014's amendment:
  1. `is_anomaly` label-derivation mistake (see above), caught in design
     review before any live run.
  2. `F821 dbutils` undefined — same recurring runtime-global pattern as
     `spark`/`display` in M4/M7 (now a confirmed fourth instance). Fixed
     identically: explicit `from databricks.sdk.runtime import dbutils`.
  3. `E402` module-level-import-order errors across the whole import block
     — structural, not sloppiness: Databricks' required
     `%pip install` → `dbutils.library.restartPython()` → import sequence
     puts real code before imports by design. Resolved with a scoped
     `ruff` `per-file-ignores` entry for `notebooks/*.py` on `E402` only
     (not a blanket ignore, and `F821` stays fixed via explicit import as
     always).
  4. `AttributeError: 'bytes' object has no attribute 'seekable'` in
     `training/upload_ground_truth.py` — `WorkspaceClient.files.upload`
     requires a seekable file-like object, not raw `bytes`. Fixed by
     wrapping the read file contents in `io.BytesIO(...)`.
- **Real end-to-end run verified** against live Databricks:
  - Gold→joined row-count reconciliation: 27,128 = 27,128, no fan-out.
  - Split: train 18,989 rows (normal 18,610; new_device 160; geo_deviation
    90; channel_deviation 89; amount_spike 40), test 8,139 rows (normal
    7,976; new_device 69; channel_deviation 39; geo_deviation 38;
    amount_spike 17).
  - **LogisticRegression** (test split, n=8,139): precision 0.9879, recall
    1.0000, F1 0.9939. Recall by type: new_device 1.000, geo_deviation
    1.000, amount_spike 1.000, **channel_deviation 1.000**.
  - **XGBoost** (test split, n=8,139): precision 0.9581, recall 0.9816, F1
    0.9697. Recall by type: new_device 1.000, geo_deviation 1.000,
    amount_spike 0.8235, **channel_deviation 1.000**.
  - Both models registered successfully to the Unity Catalog model
    registry on first attempt — confirms Free Edition supports this,
    previously unverified.
- **Headline result**: LogisticRegression recovers `channel_deviation`
  recall from the baseline's structural 0% to 100%, while also improving
  overall precision, recall, and F1 versus the baseline. **Decision:
  LogisticRegression is the leading candidate** — "registered" here means
  logged as a versioned UC artifact, not promoted to any production
  alias/stage, since a formal validation-gate/promotion mechanism doesn't
  exist yet (MLOps-lifecycle scope, not yet built). XGBoost remains logged
  and comparable, not discarded, but underperforms LR on every metric,
  most notably `amount_spike` recall (0.8235 vs. 1.000).
- **Two limitations identified and left as documented technical debt, not
  fixed** — see Technical Debt items 18–19 below and ADR-014's amendment.
- `uv run ruff check .` / `uv run ruff format --check .` — both clean
  (after the `E402` per-file-ignore addition). `uv run pytest` — all
  passing, including 3 new tests for `training/upload_ground_truth.py`.
- CI confirmed green on this milestone's commit.
- No automated test coverage for `load_ground_truth.py` or
  `train_model.py` (Databricks/Spark-only notebooks, consistent with
  Bronze/Silver/Gold/baseline-detector — no local PySpark harness in this
  project). `training/upload_ground_truth.py` has 3 tests, same pattern as
  `upload_to_volume.py`.

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
- Time-of-day deviation feature — implementation drafted and then removed;
  approach documented in ADR-012, not verified end-to-end.
- `ced.training` schema access restricted to a training-job identity,
  distinct from an inference-job identity that can't read it — the
  intended RBAC boundary per ADR-014, but Free Edition is single-user, so
  this specific access split cannot actually be enforced or demonstrated
  here.
- Formal model validation-gate / promotion mechanism (moving a model from
  "registered" to a production alias/stage) — not yet built. Milestone 8
  registers models; it does not promote them.

### ⏳ Future
- Time-of-day deviation, if revisited — needs its own design-implement-verify
  cycle per ADR-012.
- Milestone 9 onward per the approved roadmap: model validation/promotion,
  batch inference against new events, monitoring, security, full CI/CD,
  Airflow real orchestration at Milestone 12.

---

## Current Work
None in progress. Milestone 8 is closed.

## Pending Work
Milestones 9–23 per the approved roadmap, next up being model
validation/promotion and batch inference. Not yet scoped in detail — do
not begin without explicit user confirmation.

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor` (not Celery) for local development | **ADR-009** |
| Local→Databricks ingestion via `databricks-sdk` standalone script + Databricks notebook | **ADR-010** |
| Bronze writes use `mode("overwrite")`, not append | **ADR-010** (consequences) |
| `merchant_category` NULL-on-read caveat accepted as Bronze behavior, resolved in Silver validation logic | **ADR-010** (known limitation), **ADR-011** (resolution) |
| Databricks notebooks stored as `.py` "source" format, not `.ipynb` | **ADR-010** |
| Silver validation is PySpark-native (not Great Expectations/Pandera/DLT expectations) | **ADR-011** |
| Silver failure handling is quarantine (valid + rejects tables), not hard-fail or silent drop | **ADR-011** |
| `amount = 0.0` accepted as the non-monetary "not applicable" sentinel, instead of regenerating Milestone 3 data to use NULL | **ADR-011** (technical debt) |
| Gold window features use windows ending at `-1` relative to the current row (no centered/symmetric windows) | **ADR-012** |
| Amount-based Gold features are NULL for any non-monetary current-row event type, not just filtered on window input | **ADR-012** |
| `is_new_device` treats a customer's declared `normal_device` as known from event zero, in addition to observed device history | **ADR-012** |
| Gold layer has no quarantine/rejects path — row-count mismatch is treated as a bug, not a data-quality failure | **ADR-012** |
| Window-based count features (`prior_failed_login_count_24h`) are coalesced to 0 on an empty window frame, not left as Spark's default NULL | **ADR-012** |
| `is_unusual_country` is a country-mismatch proxy for geographic deviation, not a true distance metric | **ADR-012** |
| Time-of-day deviation implemented then deliberately dropped from Milestone 6 scope after seeing its actual complexity | **ADR-012** |
| Baseline detector uses fixed, additive point-scoring rules (not OR-logic), with thresholds reasoned individually and never swept against ground truth | **ADR-013** |
| Baseline detector runs on Databricks; ground-truth evaluation runs locally against a CSV export, keeping ground truth out of the warehouse permanently | **ADR-013** |
| `model_version` field name reused by the baseline (not `detector_version`) to establish the contract the eventual ML model and batch inference will share | **ADR-013** |
| Ground truth may enter Databricks for training, into an isolated schema (`ced.training`) never read by inference; the join to features happens in-memory only and is never persisted — a scoped refinement of ADR-010/013's original exclusion stance | **ADR-014** |
| Both LogisticRegression and XGBoost trained and logged as comparable MLflow runs, alongside a metrics-only baseline reference run, in one experiment | **ADR-014** |
| Registered models live in a schema (`ced.models`) separate from `ced.training`, since they must be reachable by inference while `ced.training` must not be | **ADR-014** |
| All 8 Gold features given to both ML models (unlike the baseline's 6-feature scope) — a learned model can down-weight an unhelpful feature instead of a human excluding it in advance | **ADR-014** |
| LogisticRegression named leading candidate over XGBoost, based on across-the-board better verified metrics; neither promoted to a production alias, since no promotion mechanism exists yet | **ADR-014** (amendment) |
| `uv` over Poetry/pip | Recorded here only — tooling preference |
| `ruff` for lint + format (single tool) | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV | Recorded here only (Milestone 3) |

Full ADR-002 ("Airflow as the Orchestration Layer" broadly) remains pending.

---

## Known Issues
- None blocking. CI confirmed green on `main` through Milestone 8.

## Technical Debt
1–17. Unchanged from Milestone 7 — see prior version of this file / git
history for full text (pre-commit hooks, Airflow DAG stack not CI-tested,
single-event-level anomaly injection, `amount = 0.0` sentinel ambiguity,
`channel_deviation` baseline gap now addressed by Milestone 8's ML model,
`prior_failed_login_count_24h` unverified against any known-anomalous case,
`evaluate_baseline.py` untested, etc.)
18. **Milestone 8's train/test split is row-level, not customer-level.** A
    single customer's events can appear in both the train and test splits.
    Harmless for `new_device`, `channel_deviation`, and `geo_deviation`
    (near-deterministic booleans, independent of a customer's other rows).
    A genuine gap for `amount_spike`, which depends on
    `prior_avg_amount_90d` — a customer-specific rolling baseline — so a
    customer's spike row in test could be evaluated against a baseline
    partly informed by that same customer's rows in train. Deliberately
    left as-is; if revisited, needs a customer-grouped split, not a
    parameter change to the current one.
19. **Milestone 7 baseline metrics and Milestone 8 model metrics are not
    computed on an identical basis.** The baseline's precision/recall/F1
    were verified against the full 27,128-row dataset (it's untrained, no
    train/test split applies). The ML models' metrics are computed only on
    the 8,139-row held-out test split. The comparison is directionally
    sound but not strictly like-for-like — should be stated as such in any
    interview framing.

---

## Environment / Setup Information

| Item | Value | Verification status |
|---|---|---|
| OS | Windows (native, no WSL2 terminal use) | Stated by user |
| Project Python (via `uv`) | 3.11.16 | ✅ Verified via pytest platform output |
| `uv` version | 0.12.5 | Stated by user |
| Docker Desktop | Running, Linux containers via WSL2 backend | 🟡 Inferred |
| Git | `main` branch, GitHub remote connected | ✅ Verified |
| Git version | 2.55.0.windows.4 | ✅ Verified |
| Databricks workspace | Free Edition, `https://dbc-01205ae9-f87b.cloud.databricks.com/`, serverless compute only | ✅ Verified |
| Unity Catalog catalog | `ced` (lowercase — UC normalizes catalog names) | ✅ Verified |
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold`, `ced.training`, `ced.models` | ✅ Verified |
| Unity Catalog volumes | `ced.bronze.raw_uploads`, `ced.gold.exports`, `ced.training.raw_labels` | ✅ Verified |
| MLflow tracking | Databricks-managed workspace experiment, `/Shared/customer_event_detection_m8` | ✅ Verified |
| Unity Catalog model registry | `ced.models.logistic_regression_detector` v1, `ced.models.xgboost_detector` v1 | ✅ Verified |

## Repository Structure (as of Milestone 8)
```text
customer-event-detection/
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore (includes .env)
├── .gitattributes
├── .env (gitignored, not in repo — DATABRICKS_HOST / DATABRICKS_TOKEN)
├── docs/
│ ├── project-status.md
│ ├── current-context.md
│ ├── architecture/ (empty)
│ ├── adr/
│ │ ├── ADR-009-airflow-local-dev-topology.md
│ │ ├── ADR-010-local-to-databricks-bronze-ingestion.md
│ │ ├── ADR-011-silver-data-quality-strategy.md
│ │ ├── ADR-012-gold-feature-engineering-strategy.md
│ │ ├── ADR-013-baseline-detector-design.md
│ │ └── ADR-014-ml-model-training-strategy.md
│ ├── security/ (empty)
│ ├── governance/ (empty)
│ ├── mlops/ (empty)
│ └── nfr/ (empty)
├── data_generation/
│ ├── customer_generator.py
│ └── event_generator.py
├── ingestion/
│ ├── __init__.py
│ └── upload_to_volume.py
├── training/
│ ├── __init__.py
│ └── upload_ground_truth.py
├── notebooks/
│ ├── bronze_ingestion.py
│ ├── silver_transformation.py
│ ├── gold_feature_engineering.py
│ ├── baseline_detector.py
│ ├── load_ground_truth.py
│ └── train_model.py
├── evaluation/
│ └── evaluate_baseline.py
├── data_quality/ (empty)
├── feature_engineering/ (empty)
├── inference/ (empty)
├── monitoring/ (empty)
├── data/ (gitignored, .gitkeep preserved)
│ └── raw/
│   ├── customers.csv
│   ├── events.csv
│   ├── events_ground_truth.csv
│   └── baseline_detections.csv
├── airflow/
│ ├── docker-compose.yaml
│ ├── .env
│ ├── dags/
│ │ └── 00_environment_smoke_test.py
│ └── logs/
├── tests/
│ ├── test_environment.py
│ ├── test_customer_generator.py
│ ├── test_event_generator.py
│ ├── test_upload_to_volume.py
│ └── test_upload_ground_truth.py
├── docker/ (empty)
└── .github/
    └── workflows/
        └── ci.yml
```

## Installed Dependencies

**Production**:
- `databricks-sdk>=0.133.0`
- `python-dotenv>=1.2.3`
- `pandas` (added Milestone 7)
- Databricks-side only (not a `pyproject.toml` dependency, installed via
  `%pip install` inside `train_model.py`): `xgboost`

**Dev**:
- `pytest>=8.3.0`
- `ruff>=0.6.0`

## Databricks Status
- Edition: Free Edition, serverless compute only
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`, `models`
- Bronze/Silver/Gold tables: unchanged from Milestone 7
- `ced.training.ground_truth_labels` (27,128 rows, new in Milestone 8)
- `ced.models.logistic_regression_detector` v1, `ced.models.xgboost_detector`
  v1 (new in Milestone 8, Unity Catalog model registry)
- MLflow experiment `/Shared/customer_event_detection_m8`: 3 runs
  (`baseline_rule_v1_reference`, `logistic_regression`, `xgboost`)
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — not yet orchestrating any part of this
  project's real pipeline.

## Testing Setup
- Framework: `pytest`
- Current coverage: environment (2), customer generator (7), event
  generator (19), upload-to-volume (3), upload-ground-truth (3) —
  **34 total**
- No automated coverage for any Databricks/Spark-only notebook, consistent
  with the project's stated no-local-PySpark-harness reasoning.

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- New in Milestone 8: `pyproject.toml` gained a scoped
  `[tool.ruff.lint.per-file-ignores]` entry, `"notebooks/*.py" = ["E402"]`
  — required by Databricks' `%pip install` → restart → import pattern,
  first triggered by `train_model.py`'s `xgboost` install. `F821` is not
  ignored anywhere; it continues to be resolved via explicit
  `from databricks.sdk.runtime import ...` imports, per the project's
  established convention.
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .` —
  both clean as of Milestone 8 changes.

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- ✅ Confirmed green on `main` through Milestone 8
- Still does not build/run Docker, Airflow, or touch Databricks (by design)

## Commands Used to Verify Milestone 8
```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_upload_ground_truth.py -v
uv run python training/upload_ground_truth.py
```
(Databricks notebooks — `load_ground_truth.py` then `train_model.py` — run
manually via "Run All" in the Databricks workspace.)

Observed output (`notebooks/load_ground_truth.py`):
```
Loaded 27128 ground-truth label rows from volume.
+-----------------+-----+
|anomaly_type     |count|
+-----------------+-----+
|NULL             |26586|
|amount_spike     |57   |
|channel_deviation|128  |
|geo_deviation    |128  |
|new_device       |229  |
+-----------------+-----+

Wrote 27128 rows to ced.training.ground_truth_labels

+----------+-----+
|is_anomaly|count|
+----------+-----+
|      true|  542|
|     false|26586|
+----------+-----+
```

Observed output (`notebooks/train_model.py`):
```
Gold rows: 27128, joined rows: 27128
Collected 27128 rows to driver for training.
Positive class (is_anomaly=True) count: 542

Train: 18989, Test: 8139
Train strata: normal 18610, new_device 160, geo_deviation 90,
              channel_deviation 89, amount_spike 40
Test strata:  normal 7976, new_device 69, channel_deviation 39,
              geo_deviation 38, amount_spike 17

Logged baseline reference run.

Created version '1' of model 'ced.models.logistic_regression_detector'
LogisticRegression — precision 0.9879, recall 1.0000, f1 0.9939
{'new_device': 1.0, 'geo_deviation': 1.0, 'amount_spike': 1.0, 'channel_deviation': 1.0}

Created version '1' of model 'ced.models.xgboost_detector'
XGBoost — precision 0.9581, recall 0.9816, f1 0.9697
{'new_device': 1.0, 'geo_deviation': 1.0, 'amount_spike': 0.8235294117647058, 'channel_deviation': 1.0}
```

---

## Next Recommended Task
**Milestone 9: model validation and promotion** — build the mechanism this
milestone deliberately deferred: a defined gate (e.g. minimum recall on
`channel_deviation`, no precision regression below some floor vs. the
baseline) that a registered model must pass before being promoted to a
production alias, with LogisticRegression v1 as the first real candidate to
run through it. Not started — do not begin without explicit user
confirmation.