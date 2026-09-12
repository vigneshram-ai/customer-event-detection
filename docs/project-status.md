# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 10_

_Milestone 10 status: IMPLEMENTED AND VERIFIED — a batch inference
notebook loads `ced.models.logistic_regression_detector@champion` via
`mlflow.pyfunc.load_model` (generic interface), resolves the alias to a
concrete version number at scoring time, scores a reproducible random
sample (n=500, seed=42) of `ced.gold.customer_events_features`, and
writes results to a new `ced.inference.detection_results` table in the
`model_version`-tagged contract format established since Milestone 7.
See ADR-016 for the full design, including the deliberate scope decision
to score a sample of existing Gold data rather than genuinely new events
or the exact Milestone 8 held-out split, and the `fillna(0)`
train/serve-parity reasoning._

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified

**Milestones 1–8** — unchanged from prior status; see git history / earlier
versions of this file for full detail. Summary: repo/environment setup,
synthetic customer and event generators (1,000 customers, 27,128 events,
542 injected anomalies), Bronze ingestion, Silver validation, Gold feature
engineering (8 features, leakage-safe windows), rule-based baseline
(precision 1.0000, recall 0.7435, F1 0.8529), and LogisticRegression +
XGBoost trained on the 8 Gold features (precision 0.9879/recall
1.0000/F1 0.9939 and precision 0.9581/recall 0.9816/F1 0.9697
respectively), both registered to Unity Catalog.

**Milestone 9 — Model validation gate and promotion**
- Design decisions resolved and documented in ADR-015: gate threshold
  selection, alias-based promotion, champion/challenger/
  previous_champion/archived alias semantics (project-defined
  conventions, not UC built-ins), F1 comparison with ties favoring the
  incumbent, deliberate exclusion of XGBoost from this milestone's gate.
- `notebooks/validate_and_promote_model.py` resolves the latest
  registered version of `logistic_regression_detector` dynamically,
  reads already-logged MLflow metrics, applies the three-check gate, and
  promotes via alias on pass.
- Real run verified against live Databricks (Free Edition): all three
  gate checks passed (`recall_channel_deviation` 1.0000, `recall`
  1.0000, `precision` 0.9879); no existing champion, so v1 was promoted
  directly. Final alias state: `champion -> v1`.
- Confirmed Free Edition supports `set_registered_model_alias` /
  `get_registered_model(...).aliases`.
- Three real design gaps caught and corrected before implementation
  finalized (run-to-version mapping, champion-only promotion, backwards
  challenger-assignment timing) — full detail retained in ADR-015 and
  prior versions of this file.

**Milestone 10 — Batch inference**
- **Design decisions resolved and documented in ADR-016**, covering: the
  choice to score a reproducible sample of existing Gold data rather
  than genuinely new events or the exact Milestone 8 held-out split
  (with the trade-off explicitly named: this run is not a performance
  measurement); generic `pyfunc.load_model` loading with a documented,
  sklearn-specific unwrap (`_model_impl.sklearn_model`) to obtain
  `predict_proba`; the decision to keep `detection_score` as a
  first-class output rather than relying on the coincidence that the
  0.5 threshold matches sklearn's own default class boundary; and the
  `fillna(0)` train/serve-parity reasoning (including why the resulting
  ambiguity between two distinct NULL causes is judged safe for this
  dataset).
- **`notebooks/batch_inference.py`** — new Databricks notebook.
  Resolves `ced.models.logistic_regression_detector@champion` to a
  concrete version number via `MlflowClient.get_model_version_by_alias`
  and stamps every output row with that resolved version (not the
  alias), so records stay correctly attributed even if `champion` later
  moves. Loads the model via `mlflow.pyfunc.load_model`, unwraps to the
  underlying sklearn estimator for `predict_proba`, applies a fixed 0.5
  threshold, and writes to `ced.inference.detection_results`.
- **New `ced.inference` schema and `detection_results` table** created
  (`CREATE SCHEMA IF NOT EXISTS ced.inference;`), written with
  `mode("overwrite")`.
- **Real run verified** against live Databricks (Free Edition):
  - Sample scored: 500 rows (reproducible, seed 42) from
    `ced.gold.customer_events_features`.
  - Flagged: 12 of 500 (2.40%) — consistent with Milestone 3's ~2%
    anomaly injection rate, a real sanity check (not just "it ran")
    that the threshold and probability-column indexing are correct.
  - `ced.inference.detection_results` row count confirmed at 500,
    `groupBy("model_version", "detection_flag").count()` showed
    `true: 12`, `false: 488` for a single `model_version` value
    (displayed truncated as `logistic_regressi...` in the terminal;
    inferred as `logistic_regression_detector_v1` based on Milestone 9's
    confirmed state that only v1 exists and no retrain has occurred
    since — **not directly observed**, flagged here rather than silently
    assumed).
  - CI confirmed green (lint, format, tests) on this change.
- **A real bug caught and fixed during implementation, not left as
  debt**: `sk_model.predict_proba(X)` initially raised
  `ValueError: Input X contains NaN`. Traced to `amount`-based Gold
  features being structurally `NULL` for non-monetary event rows
  (ADR-012) — a pattern that must also have existed in Milestone 8's
  training data. Resolved by reading `train_model.py`'s actual
  preprocessing (`fillna(0)` on `FEATURE_COLS` before `.fit()`) and
  replicating it exactly in the inference notebook, rather than choosing
  an independent imputation strategy that could have silently
  introduced train/serve skew.
- **A design trade-off explicitly surfaced and resolved before
  implementation**: whether `pyfunc.load_model`'s generic `.predict()`
  (which would return an identical class label to the manual threshold,
  given the 0.5/sklearn-default coincidence) could replace the
  probability-based approach entirely. Rejected — `detection_score` is a
  required contract field, and relying on the coincidence would have
  silently coupled the project's threshold decision to an implicit
  library default rather than an explicit, adjustable value.

### 🟡 Implemented, Not Fully Verified
- **`validate_and_promote_model.py`'s champion-vs-challenger comparison
  branch** (Milestone 9) — implemented and reasoned in ADR-015, but not
  yet exercised against live output. Requires a second model version
  (e.g. a deliberate retrain) to verify.
- **`batch_inference.py`'s exact resolved `model_version` string** —
  inferred as `logistic_regression_detector_v1` from known registry
  state rather than directly observed in the pasted output (the
  `groupBy` table's `model_version` column was truncated). Low risk
  given only one version currently exists, but not literally confirmed.

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
- Time-of-day deviation feature — implementation drafted and then removed;
  approach documented in ADR-012, not verified end-to-end.
- `ced.training` schema access restricted to a training-job identity,
  distinct from an inference-job identity — the intended RBAC boundary
  per ADR-014, but Free Edition is single-user, so this cannot actually be
  enforced or demonstrated.
- Live/shadow evaluation for the champion/challenger pattern — the
  current implementation (Milestone 9) is one-shot batch comparison
  only; would require batch inference to exist first, which it now does
  (Milestone 10), but the live/shadow pattern itself is not implemented.
- A genuinely new/unseen event batch for inference (Option A from
  Milestone 10's design discussion: extend `event_generator.py`, append
  to Bronze, replay Silver/Gold) — documented as a future strengthening
  of the batch-inference story, not built.
- Distributed (`spark_udf`-based) batch scoring, and a custom
  `PythonModel`-based flavor-agnostic probability output — both
  discussed in ADR-016 as the "correct" path for larger-scale/
  fully-generic scoring, neither implemented.

### ⏳ Future
- Time-of-day deviation, if revisited — needs its own design-implement-verify
  cycle per ADR-012.
- Verifying the champion/challenger comparison branch with a real second
  model version.
- A genuinely new event batch (vs. the current sample-of-existing-data
  approach) for batch inference, if needed to fully support the "new
  customer events" resume claim.
- Append/dedup strategy for `ced.inference.detection_results` once
  repeated/incremental batches exist (currently `overwrite` per run).
- Milestone 11 onward per the approved roadmap: monitoring, security,
  full CI/CD, Airflow real orchestration at Milestone 12.

---

## Current Work
None in progress. Milestone 10 is closed.

## Pending Work
Milestones 11–23 per the approved roadmap. Next up is Milestone 11
(monitoring, per the roadmap ordering after batch inference), not yet
scoped in detail — do not begin without explicit user confirmation.

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
| Ground truth may enter Databricks for training, into an isolated schema (`ced.training`) never read by inference; the join to features happens in-memory only and is never persisted | **ADR-014** |
| Both LogisticRegression and XGBoost trained and logged as comparable MLflow runs, alongside a metrics-only baseline reference run, in one experiment | **ADR-014** |
| Registered models live in a schema (`ced.models`) separate from `ced.training`, since they must be reachable by inference while `ced.training` must not be | **ADR-014** |
| All 8 Gold features given to both ML models | **ADR-014** |
| LogisticRegression named leading candidate over XGBoost, based on across-the-board better verified metrics | **ADR-014** (amendment) |
| Model validation gate reads already-logged metrics (no recomputation); three thresholds — `recall_channel_deviation`/`recall` >= 0.95, `precision` >= 0.90 | **ADR-015** |
| Promotion via Unity Catalog model aliases (`champion`/`challenger`/`previous_champion`/`archived`), not deprecated stage-based promotion | **ADR-015** |
| Champion vs. challenger comparison uses F1, ties favor the incumbent champion | **ADR-015** |
| `challenger` alias assigned on gate-pass, before comparison; losers retagged `archived` | **ADR-015** |
| XGBoost deliberately excluded from Milestone 9's gate | **ADR-015** |
| Batch inference scores a reproducible sample of existing Gold data, not genuinely new events or the exact M8 held-out split — deliberate scope decision to prioritize pipeline mechanics over data governance/generation | **ADR-016** |
| Model loaded via generic `mlflow.pyfunc.load_model`, with a documented sklearn-specific unwrap (`_model_impl.sklearn_model`) to obtain `predict_proba` | **ADR-016** |
| `detection_score` kept as a required, first-class output rather than relying on the 0.5-threshold/sklearn-default coincidence to justify dropping it | **ADR-016** |
| Inference replicates `train_model.py`'s `fillna(0)` exactly, for train/serve parity; judged semantically safe given the synthetic generator's amount distribution | **ADR-016** |
| `ced.inference.detection_results` written with `mode("overwrite")` per run; no append/dedup strategy yet | **ADR-016** |
| `uv` over Poetry/pip | Recorded here only — tooling preference |
| `ruff` for lint + format (single tool) | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV | Recorded here only (Milestone 3) |

Full ADR-002 ("Airflow as the Orchestration Layer" broadly) remains pending.

---

## Known Issues
- None blocking. CI confirmed green through Milestone 10.
- The `model_version` value written by Milestone 10 was inferred from
  known registry state, not literally observed in pasted terminal output
  (truncated column display) — see Technical Debt #26.

## Technical Debt
1–19. Unchanged from Milestone 8 — see prior version of this file / git
history for full text.
20. **The champion/challenger comparison branch in
    `validate_and_promote_model.py` is implemented but not yet exercised
    against live output** — only the "no existing champion" path has run.
    Requires a second model version to verify. Not a defect; a stated
    verification gap per ADR-015.
21. **The `archived` alias only tags the single most-recently-losing
    version** — earlier losing versions remain in the registry (immutable,
    queryable by version number) but lose the alias tag once a newer
    version is archived. Deliberately left as-is.
22. **Milestone 10's batch inference scores a reproducible sample of
    existing Gold data, not genuinely new/unseen events, and not the
    exact Milestone 8 held-out test split.** A deliberate scope decision
    (ADR-016) to focus on the inference *mechanism* — alias-based
    loading, scoring, contract output — rather than data generation or
    exact train/test governance. Consequence: this run's detection
    output is not a fresh performance measurement (the batch overlaps
    training data); Milestone 8's held-out evaluation remains the
    authoritative model-performance numbers. The "batch inference
    against new customer events" resume claim is supported at the
    mechanism level, not yet at the genuinely-new-data level.
23. **`predict_proba` is obtained by unwrapping the sklearn estimator
    from the generic `pyfunc` wrapper** (`_model_impl.sklearn_model`) —
    works, but is sklearn-specific, not a flavor-agnostic pattern, and
    would not carry over unchanged to `mlflow.pyfunc.spark_udf`-based
    distributed scoring. A model logged at training time as a custom
    `PythonModel` returning probabilities directly would remove this;
    out of scope without an M8-level retrain.
24. **`ced.inference.detection_results` uses `mode("overwrite")`** — no
    accumulation of historical batches; each run replaces the prior
    one's results entirely. An append-with-dedup-by-`event_id` strategy
    would be needed once genuinely repeated/incremental batches exist.
25. **`fillna(0)` on amount-based Gold features collapses two distinct
    NULL causes** (current row non-monetary, vs. monetary row with no
    prior monetary history) into the same encoded value. Judged safe for
    this dataset — the synthetic generator never produces a genuinely
    monetary event with `amount = 0.0`, so a real prior-amount average of
    exactly 0 cannot occur — but the two causes remain structurally
    indistinguishable in the encoded features. A dedicated indicator
    feature (e.g. `has_prior_monetary_history`) would resolve this if
    ever revisited.
26. **Milestone 10's exact `model_version` output string
    (`logistic_regression_detector_v1`) was inferred from known registry
    state, not directly observed** — the pasted `groupBy` output
    truncated the column display. Low risk (only one version currently
    registered, no retrain since Milestone 9), but stated explicitly
    rather than silently treated as confirmed.

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
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold`, `ced.training`, `ced.models`, `ced.inference` | ✅ Verified (`inference` new in Milestone 10) |
| Unity Catalog volumes | `ced.bronze.raw_uploads`, `ced.gold.exports`, `ced.training.raw_labels` | ✅ Verified |
| MLflow tracking | Databricks-managed workspace experiment, `/Shared/customer_event_detection_m8` | ✅ Verified |
| Unity Catalog model registry | `ced.models.logistic_regression_detector` v1 (alias `champion`), `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified |
| `ced.inference.detection_results` | 500 rows, 12 flagged (2.40%) | ✅ Verified |

## Repository Structure (as of Milestone 10)
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
│ │ ├── ADR-014-ml-model-training-strategy.md
│ │ ├── ADR-015-model-validation-and-promotion.md
│ │ └── ADR-016-batch-inference-design.md
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
│ ├── train_model.py
│ ├── validate_and_promote_model.py
│ └── batch_inference.py
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

Note: `inference/` (local package directory) remains empty — Milestone
10's inference logic lives entirely in the Databricks notebook
(`notebooks/batch_inference.py`), consistent with the project's pattern
of Databricks/Spark-only logic having no local Python module
counterpart (same as the other notebooks).

## Installed Dependencies

**Production**:
- `databricks-sdk>=0.133.0`
- `python-dotenv>=1.2.3`
- `pandas` (added Milestone 7)
- Databricks-side only (not a `pyproject.toml` dependency): `xgboost`
  (Milestone 8), `mlflow` (Databricks-managed runtime, used Milestones
  8–10)

**Dev**:
- `pytest>=8.3.0`
- `ruff>=0.6.0`

No new local dependencies introduced in Milestone 10 —
`batch_inference.py` uses `mlflow`, `mlflow.tracking.MlflowClient`, and
PySpark, all already available in the Databricks-managed runtime.

## Databricks Status
- Edition: Free Edition, serverless compute only
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`,
  `models`, `inference` (new in Milestone 10)
- Bronze/Silver/Gold/training tables: unchanged from Milestone 8
- `ced.models.logistic_regression_detector` v1 — alias `champion`
  (unchanged since Milestone 9)
- `ced.models.xgboost_detector` v1 — no alias (unchanged)
- `ced.inference.detection_results` — new in Milestone 10, 500 rows,
  written via `mode("overwrite")`
- MLflow experiment `/Shared/customer_event_detection_m8`: unchanged,
  Milestone 10 reads from it (via the registered model), does not add
  runs
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — not yet orchestrating any part of this
  project's real pipeline.

## Testing Setup
- Framework: `pytest`
- Current coverage: environment (2), customer generator (7), event
  generator (19), upload-to-volume (3), upload-ground-truth (3) —
  **34 total**, unchanged in Milestone 10
- No automated coverage for any Databricks/Spark-only notebook,
  consistent with the project's stated no-local-PySpark-harness pattern
  — `batch_inference.py` follows this same pattern.

## Linting/Formatting Setup
- Unchanged from Milestone 8. No new lint/format exceptions required in
  Milestone 10 — `batch_inference.py` needed no `%pip install`, so the
  `E402` per-file-ignore situation does not recur here.

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- ✅ Confirmed green on `main` through Milestone 10 (per user
  confirmation); Milestone 10 introduces no new testable Python module
  (Databricks notebook only), consistent with the pattern since
  Milestone 9.
- Still does not build/run Docker, Airflow, or touch Databricks (by design)

## Commands Used to Verify Milestone 10
(Databricks: `CREATE SCHEMA IF NOT EXISTS ced.inference;` run in a SQL
cell, followed by `notebooks/batch_inference.py` run manually via
"Run All" in the Databricks workspace; no local commands required for
this milestone.)

Observed output (`notebooks/batch_inference.py`):
```text
Flagged 12 of 500 scored events (2.40%)

Rows in ced.inference.detection_results: 500
+--------------------+--------------+-----+
|       model_version|detection_flag|count|
+--------------------+--------------+-----+
|logistic_regressi...|          true|   12|
|logistic_regressi...|         false|  488|
+--------------------+--------------+-----+
```