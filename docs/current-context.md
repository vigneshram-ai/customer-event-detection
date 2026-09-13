# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–11 are **complete and verified**. Milestone 11 (monitoring) built a
Databricks notebook that runs Evidently `DataDriftPreset` and `DataSummaryPreset`
reports against `ced.inference.detection_results` (treated, per explicit scope
decision, as the batch under monitoring), persists flattened, human-readable
results to a new `ced.monitoring.batch_quality_report` table, and renders both
reports as inline HTML. Milestone 12 (Airflow real orchestration, per the roadmap
ordering: batch inference → monitoring → security → full CI/CD → Airflow
orchestration) has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 11.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with
  only the temporary smoke-test DAG — deliberately deferred to Milestone 12.
- All Milestone 1–10 artifacts unchanged except one documentation
  correction (see Milestone 11 decisions below): generators, ingestion,
  Bronze/Silver/Gold, baseline detector, ground-truth loading,
  LogisticRegression/XGBoost training, validation gate and alias-based
  promotion, and batch inference are all otherwise as previously recorded.
- **New in Milestone 11**: `notebooks/monitoring.py` — a Databricks
  notebook requiring `%pip install evidently` (not in the managed
  runtime), following the established install → `dbutils.library.restartPython()`
  → import pattern, covered by the existing `notebooks/*.py` E402
  per-file-ignore (no `pyproject.toml` change needed).
- **Databricks side, new state**:
  - New schema `ced.monitoring` created.
  - New table `ced.monitoring.batch_quality_report` — append-mode,
    columns `run_id`, `scored_at`, `metric_category`, `metric_name`,
    `value`, `threshold`, `status`.
  - **Two independent notebook runs** (distinct `run_id`s), 79 metric
    rows each (9 drift + 70 data-quality/summary), 158 rows total. All
    metric values identical across both runs — confirms deterministic
    computation and correct append accumulation.
  - No other Databricks-side state changed. `ced.inference.detection_results`,
    `ced.models.*` aliases, `ced.training` all unchanged from Milestone 10.
- `pyproject.toml` unchanged — the existing `"notebooks/*.py" = ["E402"]`
  per-file-ignore already covers `monitoring.py`'s install/restart
  pattern; no new dependency added there since `evidently` is
  Databricks-side only (same pattern as `xgboost`/`mlflow`).

## Key Design Decisions From Milestone 11 (do not silently revisit — full detail in ADR-017)
- **Evidently used directly for every monitoring metric** — no
  hand-rolled statistics (an earlier draft self-computed PSI; rejected
  per explicit direction in favor of the real library). Two Evidently
  `Report`s: `DataDriftPreset()` (current vs. reference, 8 Gold
  features) and `DataSummaryPreset()` (current batch only, 8 features +
  `detection_score` + `detection_flag`).
- **Auto-selected drift tests, not forced PSI.** An initial design
  forced `method="psi"` uniformly, reasoning it was needed for
  cross-feature comparability. Corrected after reviewing a real sample
  Evidently output: auto-selected per-column tests (Wasserstein
  distance for numerical, Jensen-Shannon distance for categorical in
  this run) already roll up into a calibrated Drifted/Not-Drifted
  boolean per column plus an aggregate dataset-level drift share —
  comparability was never actually PSI-dependent. PSI's specific
  relevance to banking/credit-risk monitoring is retained as domain
  context, not as the implemented method.
- **`ced.inference.detection_results` (Milestone 10's batch) is treated
  as the batch under monitoring**, per explicit scope decision — the
  sample-vs-new-data distinction (Technical Debt #22) was judged a
  data-generation convenience, not worth re-litigating for this
  milestone. **Consequence, stated explicitly**: because this batch is
  a subset of the reference population it's compared against,
  near-zero drift is the *expected, correct* result — a negative
  control confirming the monitoring mechanism works, not a genuine
  "checked for drift in the wild and found none."
- **A real M10 inaccuracy was found and corrected, not silently
  patched.** `ced.inference.detection_results`'s persisted
  `FEATURE_COLUMNS` are **raw (non-imputed) Gold values**, not the
  `fillna(0)`-imputed values actually fed to the model. Milestone 10's
  `fillna(0)` fix (ADR-016) was applied to the transient scoring matrix
  only and never propagated to the output write — this contradicts what
  ADR-016 and this file previously claimed about Milestone 10's stored
  features (see the corrected Milestone 10 section below). The
  monitoring notebook applies `fillna(0)` identically to both reference
  and current feature sets, replicating `train_model.py`'s exact
  preprocessing, independent of this uncorrected upstream table.
  Logged as new Technical Debt #28.
- **Evidently's `report.dict()` schema was verified empirically, not
  assumed.** Two earlier extraction attempts guessed wrong field names
  (`metric_id` as a readable name; then no `name` field found at all).
  The real schema: each metric has `id` (hash, for linking) and
  `metric_name` (human-readable, e.g.
  `ValueDrift(column=prior_event_count_7d,method=Wasserstein distance (normed),threshold=0.1)`);
  each test links back via `test["metric_config"]["metric_id"]` and
  carries a `description` stating the measured value against its
  threshold in plain language — used directly as the persisted
  `threshold` field. A defensive raw-JSON fallback remains for
  resilience against future Evidently schema changes (Technical Debt
  #27).
- **Two `FAIL` statuses in the persisted quality metrics were
  interpreted, not just reported.** `DuplicatedRowCount() = 18`: the
  checked columns exclude identifiers (`event_id`/`customer_id`), and
  several features are sparse/low-cardinality, so distinct events
  legitimately sharing a feature vector is expected — not a data
  integrity bug. `AlmostConstantColumnsCount() = 5`: the 5 flagged
  columns (`is_new_device`, `is_unusual_channel`, `is_unusual_country`,
  `detection_flag`, `prior_failed_login_count_24h`) are rare-event
  indicators by design — low prevalence is the intended signal. Both
  documented explicitly in ADR-017 as expected/benign rather than
  silently dismissed or silently treated as defects.
- **Verified result**: two independent runs, 79 rows each (9 drift + 70
  quality/summary), 158 total, identical values across runs. Drift: 0
  of 8 features drifted (`DriftedColumnsCount` share 0.0), all
  `ValueDrift` scores 0.006–0.064 (threshold 0.1), all
  `TestStatus.SUCCESS`. Lint and format clean (`ruff check .` /
  `ruff format --check .`). CI confirmed green.
- **No pipeline-level (orchestration) monitoring implemented** —
  deferred to Milestone 12 per roadmap ordering; monitoring
  pipeline/task success-failure/duration concepts require an
  orchestrated DAG to be meaningful, which doesn't exist yet.
- **Computed in pandas, not PySpark-native** — `Dataset.from_pandas`
  is driver-memory bound. Acceptable at the current 500-row scale;
  documented separately (see conversation / teaching note) how this
  would need to change at larger scale, not implemented.

## Correction to Milestone 10's Recorded Decisions (identified during Milestone 11)
The Milestone 10 section below previously stated that
`ced.inference.detection_results`'s persisted feature columns were
already `fillna(0)`-imputed. **This was inaccurate.** The `fillna(0)`
fix (ADR-016) was applied to the transient scoring matrix passed to
`predict_proba` only; it was never applied to the `pdf` that got
written to the output table. The persisted `FEATURE_COLUMNS` are raw
Gold values, nulls included, for amount-based features on non-monetary
rows. `detection_score`/`detection_flag` themselves are unaffected and
correct (they came from the properly-imputed scoring matrix). See
Technical Debt #28 and ADR-017. Not fixed at the source — would require
re-running `batch_inference.py`, explicitly out of scope since no
further inference runs are planned.

## Key Design Decisions From Milestone 10 (do not silently revisit — full detail in ADR-016; see correction above)
- **The batch scored is a reproducible random sample of existing
  `ced.gold.customer_events_features` (n=500, seed 42), not genuinely
  new/unseen events and not the exact Milestone 8 held-out test split.**
  This was a deliberate, discussed trade-off: an initial design explored
  generating a genuinely new synthetic event batch and replaying it
  through Bronze→Silver→Gold (which would have required moving Bronze
  from `overwrite` to `append` mode — a deviation from ADR-010 — plus a
  new `ingestion_batch` marker column), and a second design explored
  reconstructing the exact M8 test split via a one-time bootstrap script.
  Both were set aside in favor of the simpler sample-based approach, to
  keep focus on the inference *mechanism* rather than data generation or
  train/test governance. **Consequence, stated explicitly**: this run's
  detection output is not a fresh model-performance measurement — the
  batch overlaps training data. Milestone 8's held-out evaluation remains
  the authoritative performance numbers. (Milestone 11 explicitly builds
  on top of this same trade-off — see above.)
- **Model loaded via generic `mlflow.pyfunc.load_model`**, not the
  flavor-specific `mlflow.sklearn.load_model` — chosen for consistency
  with how this project would eventually need to load models at scale
  (the same interface `pyfunc.spark_udf` uses for distributed scoring).
- **`predict_proba` is obtained via a documented, sklearn-specific
  unwrap** (`pyfunc_model._model_impl.sklearn_model`), because the
  generic `pyfunc.predict()` contract only returns the sklearn class
  label, not a probability. This is explicitly *not* a generalizable
  distributed-scoring pattern — a genuinely flavor-agnostic probability
  output would require the model to be logged at training time as a
  custom `PythonModel`, which is out of scope without an M8-level
  retrain.
- **A real bug was caught and fixed via reading actual code, not
  guessing**: `predict_proba` initially raised
  `ValueError: Input X contains NaN`, traced to amount-based Gold
  features being structurally NULL for non-monetary rows (ADR-012). The
  fix was to read `train_model.py`'s actual preprocessing and replicate
  it exactly (`fillna(0)` on `FEATURE_COLS`) rather than choosing an
  independent imputation strategy — **this fix was applied to the
  scoring matrix only; it was not propagated to the persisted output
  columns, per the correction above.**
- **`model_version` is resolved to a concrete version number at scoring
  time** (e.g. `logistic_regression_detector_v1`), not written as the
  alias `champion` — so historical detection records stay correctly
  attributed even if `champion` later moves to a different version.
- **Output written to a new `ced.inference` schema**,
  `detection_results` table, with `mode("overwrite")` — each run
  represents "the current batch scored." No append/dedup-by-`event_id`
  strategy exists yet for accumulating multiple historical batches
  (Technical Debt #24).
- **Verified result**: 500 rows scored, 12 flagged (2.40%) — consistent
  with Milestone 3's ~2% anomaly injection rate. CI confirmed green.

## Key Design Decisions From Milestone 9 (do not silently revisit — full detail in ADR-015)
- **Gate reads already-logged metrics only — never recomputes.** The
  notebook resolves the *latest* registered version of
  `logistic_regression_detector` dynamically via `search_model_versions`
  (not a hardcoded run name or version number), so it stays correct across
  future retrains without code changes.
- **Three gate thresholds**: `recall_channel_deviation >= 0.95`,
  `recall >= 0.95`, `precision >= 0.90`.
- **Promotion is alias-based** (`champion`/`challenger`/
  `previous_champion`/`archived`), not stage-based.
- **Champion/challenger comparison metric is F1** — ties favor the
  incumbent champion.
- **`challenger` is assigned immediately on gate-pass, before any
  comparison happens.**
- **Verified result**: first-ever run — all three gate checks passed,
  v1 promoted directly to `champion`.
- **Explicitly NOT yet verified**: the champion-vs-challenger comparison
  branch has never run against live output (Technical Debt #20).

## Key Design Decisions From Milestones 5–8
Unchanged from prior snapshots — see `docs/project-status.md` and
ADR-011 through ADR-014 for full detail (Silver quarantine strategy,
Gold leakage-boundary windows, baseline additive scoring, ground-truth
isolation to `ced.training`, LogisticRegression selected as leading
candidate).

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models`, `inference`, `monitoring` (new in Milestone 11)
- Volumes: `bronze.raw_uploads`, `gold.exports`, `training.raw_labels`
- MLflow: Databricks-managed workspace experiment
  `/Shared/customer_event_detection_m8`
- Model registry aliases: `ced.models.logistic_regression_detector` v1 →
  `champion`; `ced.models.xgboost_detector` v1 → no alias (unchanged)
- `ced.inference.detection_results`: 500 rows, 12 flagged, unchanged
  since Milestone 10 (feature-column caveat: see correction above)
- `ced.monitoring.batch_quality_report`: 158 rows (2 runs × 79 metrics),
  new in Milestone 11
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost`, `mlflow`, `evidently` are Databricks-side only, not
  `pyproject.toml` dependencies.
- PAT stored in `.env` (git-ignored)

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written.
- Time-of-day deviation — designed and partially implemented, then
  removed.
- Bronze, Silver, and Gold processing are all manual (no Airflow
  orchestration) — deferred to Milestone 12.
- **`ced.training` access restricted to a training-job identity — 📐
  DESIGNED ONLY, cannot be enforced on Free Edition (single-user).**
- **Milestone 8's train/test split is row-level, not customer-level** —
  Technical Debt #18.
- **Baseline (M7) and ML model (M8) metrics are on different evaluation
  bases** — Technical Debt #19.
- **Milestone 9's champion-vs-challenger comparison branch is unverified
  against live output** — Technical Debt #20.
- **The `archived` alias only tracks the single most-recent losing
  version** — Technical Debt #21.
- **Live/shadow evaluation for champion/challenger doesn't exist** — 📐
  DESIGNED as a future extension in ADR-015.
- **Milestone 10's batch is a sample of existing Gold data, not
  genuinely new/unseen events** — Technical Debt #22. Now also the
  reason Milestone 11's near-zero drift result is a negative control,
  not a genuine "no drift" finding — see ADR-017.
- **`predict_proba` extraction via sklearn-specific unwrap** — Technical
  Debt #23.
- **`ced.inference.detection_results` uses `overwrite`, no historical
  accumulation** — Technical Debt #24.
- **`fillna(0)` collapses two distinct NULL causes in amount-based
  features** — Technical Debt #25.
- **Milestone 10's exact `model_version` output string was inferred, not
  directly observed** — Technical Debt #26.
- **NEW — Monitoring's Evidently-dict extraction depends on an internal,
  non-public schema** — Technical Debt #27. May break on a future
  Evidently version bump; defensive raw-JSON fallback exists but won't
  restore readability automatically.
- **NEW — `ced.inference.detection_results`'s persisted feature columns
  are raw, not imputed** — Technical Debt #28. Corrects the Milestone 10
  claim to the contrary. Not fixed at the source (no further inference
  runs planned); monitoring notebook applies correct imputation
  independently.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Claude Desktop workflow: never assume direct local file/execution access.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  Milestone 11's two `FAIL` statuses (`DuplicatedRowCount`,
  `AlmostConstantColumnsCount`) are the latest instance: both required
  domain interpretation to correctly judge as benign rather than being
  accepted or rejected at face value.
- **When implementation reveals a preprocessing dependency between
  stages, go read the actual upstream code rather than choosing an
  independent approach** — this pattern caught the Milestone 10
  imputation gap during Milestone 11 (NULLs surfaced by an assertion,
  traced to the actual `batch_inference.py` behavior, not guessed at).
- **Verify library internals empirically before writing extraction code
  against them** — two incorrect guesses at Evidently's `report.dict()`
  schema were made before the real structure was inspected directly;
  the working extraction code is based on confirmed, observed fields,
  not documentation or assumption.
- **Design proposals should be treated as genuinely open to challenge,
  not rubber-stamped** — Milestone 11's design went through multiple
  rounds of correction (forced PSI → auto-select, after direct
  challenge with a real counter-example; custom stats → Evidently-only,
  per explicit direction) before being finalized.

## Immediate Next Step
Milestone 11 is closed. Next up is **Milestone 12** per the approved
roadmap: real Airflow orchestration, replacing the temporary smoke-test
DAG and formally orchestrating Bronze → Silver → Gold → training/
validation → batch inference → monitoring. Not yet scoped in detail —
do not begin without explicit user confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009` through `ADR-016` — see prior snapshots for
  individual summaries (unchanged this milestone)
- `docs/adr/ADR-017-monitoring-strategy.md` — Evidently tool choice,
  auto-select-vs-PSI correction, reference/current imputation parity,
  the Milestone 10 feature-imputation correction, extraction-schema
  verification, and the two interpreted `FAIL` statuses
- `README.md` — public-facing summary (kept minimal, accurate)