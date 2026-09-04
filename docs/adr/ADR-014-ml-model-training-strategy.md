# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–8 are **complete and verified**. Milestone 8 (ML model
training) is fully closed — LogisticRegression and XGBoost trained on the 8
Gold features against Milestone 3 ground-truth labels, tracked in
Databricks-managed MLflow, both registered to the Unity Catalog model
registry. LogisticRegression recovers the Milestone 7 baseline's structural
0% recall on `channel_deviation` anomalies to 100%, while also improving
overall precision/recall/F1, and is named the leading candidate — not
promoted to production, since no formal promotion mechanism exists yet
(that's Milestone 9). Four issues were caught and fixed during
design/verification (see below and ADR-014's amendment); two further
limitations were identified and **deliberately left as documented technical
debt**, not fixed. Milestone 9 has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 8.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with only
  the temporary smoke-test DAG. Not orchestrating anything real yet —
  deliberately deferred to Milestone 12.
- `data_generation/`, `ingestion/upload_to_volume.py`,
  `training/upload_ground_truth.py` all exist and are tested (34 tests
  total, all passing), `ruff` clean.
- Notebooks `bronze_ingestion.py`, `silver_transformation.py`,
  `gold_feature_engineering.py`, `baseline_detector.py`,
  `load_ground_truth.py`, and `train_model.py` all exist and have been run
  successfully against the live Databricks Free Edition workspace. **None
  has automated test coverage** — verification is manual/observed-output
  only (no local PySpark harness in this project).
- `evaluation/evaluate_baseline.py` exists, runs locally, unchanged since
  Milestone 7.
- **Databricks side is real and verified**: workspace
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`, Unity Catalog `ced`.
  - `ced.bronze.customers` (1,000 rows), `ced.bronze.events` (27,128 rows)
  - `ced.silver.customers` (1,000 valid), `ced.silver.events` (27,128 valid)
  - `ced.gold.customer_events_features` (27,128 rows, 8 features)
  - `ced.gold.baseline_detections` (27,128 rows, Milestone 7)
  - **`ced.training.ground_truth_labels`** (27,128 rows, new in Milestone 8
    — `event_id`, `anomaly_type`, `is_anomaly`; 542 `is_anomaly=True` rows,
    matching the M3/M7-verified anomaly total exactly)
  - **`ced.models.logistic_regression_detector` v1**,
    **`ced.models.xgboost_detector` v1** (new in Milestone 8, Unity Catalog
    model registry — confirmed working on Free Edition, previously
    unverified)
  - MLflow experiment **`/Shared/customer_event_detection_m8`** (new in
    Milestone 8): 3 runs — `baseline_rule_v1_reference` (metrics-only,
    the M7 baseline's already-verified numbers, no model artifact),
    `logistic_regression`, `xgboost`
  - Volume `ced.bronze.raw_uploads` holds `customers.csv`, `events.csv` —
    NOT the ground-truth sidecar.
  - Volume `ced.gold.exports` holds the M7 baseline export.
  - **Volume `ced.training.raw_labels`** (new in Milestone 8) holds the
    uploaded `events_ground_truth.csv` — the only place ground truth
    exists on the Databricks side, isolated from `ced.gold`/`ced.bronze`.
- Compute is **serverless only** (Free Edition). `xgboost` is not
  preinstalled — Milestone 8 is the first notebook in this project needing
  `%pip install`, which required a new `ruff` per-file-ignore (see below).
- MLflow and Unity Catalog model registry are now real and verified
  (Milestone 8) — no longer "no MLflow exists yet."
- `pyproject.toml` production dependencies unchanged from Milestone 7
  (`databricks-sdk`, `python-dotenv`, `pandas`). `xgboost` is installed
  Databricks-side only, via `%pip install` inside `train_model.py`, not a
  `pyproject.toml` dependency.
- `.env` (git-ignored) holds `DATABRICKS_HOST` / `DATABRICKS_TOKEN`. Never
  commit this file or its contents.

## Key Design Decisions From Milestone 8 (do not silently revisit — full detail in ADR-014)
- **Ground-truth boundary refined, not discarded.** ADR-010/013 established
  that ground truth is deliberately excluded from Bronze uploads and the
  warehouse generally. Milestone 8 refines this: ground truth may enter
  Databricks **for training only**, into an isolated schema
  (`ced.training`) that inference paths never read. The real invariant was
  always "labels must never reach inference-facing tables," not "labels
  must never touch the platform." **`ced.training` must never be read by
  any future batch-inference process** — treat this as a hard boundary
  going forward.
- **The feature/label join is never persisted.** `train_model.py` joins
  `ced.gold.customer_events_features` and `ced.training.ground_truth_labels`
  **in-memory only**, inside the notebook's Spark session. No table
  anywhere contains both features and labels together.
- **Registered models live in `ced.models`, deliberately separate from
  `ced.training`** — models must be loadable by future inference, so they
  cannot live in the schema that's walled off from inference.
- **Both LogisticRegression and XGBoost were trained**, on all 8 Gold
  features (unlike the baseline's 6-feature scope — a learned model can
  down-weight an unhelpful feature instead of a human excluding it in
  advance). Stratified 70/30 split by `anomaly_type`, seed 42.
- **The Milestone 7 baseline was logged into the same MLflow experiment as
  a metrics-only reference run** (`baseline_rule_v1_reference`) — its
  already-verified numbers, not recomputed, and no model artifact, since
  it isn't a fitted model. This makes "did we beat the baseline" directly
  answerable in the MLflow UI.
- **Verified result: LogisticRegression is the leading candidate.**
  Test-split (n=8,139) metrics: precision 0.9879, recall 1.0000, F1 0.9939.
  Recall by type: `new_device` 1.000, `geo_deviation` 1.000, `amount_spike`
  1.000, **`channel_deviation` 1.000** (up from the baseline's 0.000).
  XGBoost also fixes `channel_deviation` (1.000) and modestly improves
  `amount_spike` over the baseline (0.8235 vs. 0.8070), but underperforms
  LR on every metric (precision 0.9581, recall 0.9816, F1 0.9697).
  **"Registered" ≠ "promoted"** — neither model has been moved to any
  production alias/stage; that mechanism doesn't exist yet (Milestone 9).
- **Two limitations identified and deliberately left as technical debt,
  not fixed** (same honesty convention as the M7 `channel_deviation` gap
  and the M5 `amount = 0.0` sentinel):
  1. **Row-level, not customer-level, train/test split.** Harmless for
     `new_device`/`channel_deviation`/`geo_deviation` (near-deterministic
     booleans), a genuine gap for `amount_spike` (depends on a
     customer-specific rolling baseline, `prior_avg_amount_90d`, so a
     customer's rows can straddle both splits). If revisited: needs a
     customer-grouped split, not a parameter tweak.
  2. **Baseline and ML metrics are not on an identical basis.** Baseline
     verified on the full 27,128-row dataset (untrained, no split
     applies); ML models verified only on the 8,139-row test split.
     Directionally sound comparison, not strictly like-for-like — say so
     in any interview framing.
- **Four issues caught, three during live verification, one in design
  review before any run:**
  1. **`is_anomaly` label-derivation mistake** — an early draft of
     `load_ground_truth.py` derived `is_anomaly` from whether
     `anomaly_type` was non-null, instead of reading the ground-truth
     CSV's actual `is_synthetic_anomaly` column. Caught by the user during
     design review, before any live run — not a live-verification catch,
     but the same "read the actual columns, don't assume" discipline.
  2. **`F821 dbutils` undefined** — same recurring runtime-global pattern
     as `spark`/`display` in M4/M7 (now a **confirmed fourth instance**).
     Fixed identically: `from databricks.sdk.runtime import dbutils`.
  3. **`E402` module-level-import-order errors** — structural, not
     sloppiness: Databricks' `%pip install` → `dbutils.library.
     restartPython()` → import sequence necessarily puts real code before
     imports. Fixed with a **scoped** `ruff` `per-file-ignores` entry,
     `"notebooks/*.py" = ["E402"]` — not a blanket ignore, and `F821`
     stays fixed via explicit import as always, not added to the ignore
     list.
  4. **`AttributeError: 'bytes' object has no attribute 'seekable'`** in
     `training/upload_ground_truth.py` — `WorkspaceClient.files.upload`
     needs a seekable file-like object. Fixed with
     `io.BytesIO(contents)` instead of passing raw `bytes`.

## Key Design Decisions From Milestone 7 (do not silently revisit — full detail in ADR-013)
- Baseline uses additive point-scoring, not OR-logic; `prior_event_count_7d`
  and `time_since_last_event_seconds` excluded from scoring (context-only).
- Thresholds fixed and individually reasoned, never swept against ground
  truth — anti-leakage decision for the baseline's role as an untuned
  reference point.
- Detector runs on Databricks; evaluation runs locally against a CSV
  export. Ground truth never uploaded to the warehouse **at that time** —
  refined in Milestone 8 to allow a training-only, isolated exception (see
  above); the evaluation-runs-locally mechanism itself is unchanged.
- `model_version` field name (not `detector_version`) is a deliberate
  contract choice, reused unchanged by the ML model/batch inference.
- Verified result: precision 1.0000, recall 0.7435, F1 0.8529. Recall by
  type: `new_device` 100%, `geo_deviation` 100%, `amount_spike` 80.7%,
  `channel_deviation` 0% (structural, since resolved by Milestone 8's
  LogisticRegression).
- Two Spark bugs caught and fixed: `array_remove(array, None)` nulling the
  whole array (fixed with `F.filter(..., isNotNull())`); `spark` runtime
  global `NameError` (fixed with explicit import — now a recurring pattern,
  four confirmed instances counting Milestone 8's `dbutils` case).

## Key Design Decisions From Milestone 6 (do not silently revisit — full detail in ADR-012)
- Gold table is event-grain, one row per Silver event.
- Leakage boundary: every window feature's `rowsBetween`/`rangeBetween`
  ends at `-1` relative to the current row — non-negotiable.
- Eight features shipped: `prior_event_count_7d`, `prior_avg_amount_90d`,
  `amount_deviation_from_prior_avg`, `is_new_device`, `is_unusual_channel`,
  `is_unusual_country`, `prior_failed_login_count_24h`,
  `time_since_last_event_seconds`.
- Time-of-day deviation designed then deliberately dropped — reusable
  draft in ADR-012, not implemented.
- Amount-feature applicability bug (fixed): NULL for non-monetary
  *current-row* event types, not just filtered window input.
- Empty-window-frame NULL bug (fixed): `F.coalesce(..., F.lit(0))` for
  count features over empty windows — general Spark behavior, recurring
  risk area for this project.
- `is_new_device`: `False` if device matches `normal_device` OR prior
  history; `True` only if neither.
- Gold has no quarantine/rejects path — row-count mismatch is a bug.

## Key Design Decisions From Milestone 5 (do not silently revisit — full detail in ADR-011)
- Silver validation is plain PySpark, not Great Expectations/Pandera/DLT.
- Quarantine failure handling: every Bronze row lands in exactly one of
  `ced.silver.<table>` or `_rejects`, reconciled on every write.
- `event_timestamp` parsed with an explicitly pinned format.
- `merchant_category` NULL valid for 6 non-monetary event types.
- `amount = 0.0` for non-monetary events accepted as the valid sentinel —
  deliberately not "fixed" at the generator. Resolved at the Gold feature
  layer (NULL for non-monetary amount features), not at the source.
- `.cache()`/`.persist()` unsupported on Free Edition serverless compute.

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models` (last two new in Milestone 8)
- Volumes: `bronze.raw_uploads`, `gold.exports`, `training.raw_labels`
  (new in Milestone 8)
- MLflow: Databricks-managed workspace experiment (new in Milestone 8)
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost` is Databricks-side only (`%pip install` inside the notebook),
  not a `pyproject.toml` dependency.
- PAT stored in `.env` (git-ignored)

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written.
- Time-of-day deviation — designed and partially implemented, then
  removed. Fresh design-implement-verify cycle if revisited.
- `amount = 0.0` ambiguity at Silver — intentionally left as-is at that
  layer; resolved at Gold.
- Bronze, Silver, and Gold processing are all manual (no Airflow
  orchestration) — deferred to Milestone 12.
- `prior_failed_login_count_24h` baseline rules have zero support in
  current ground truth.
- **`ced.training` access restricted to a training-job identity, distinct
  from an inference-job identity — the intended RBAC boundary per
  ADR-014, but Free Edition is single-user, so this cannot actually be
  enforced or demonstrated. Documented as 📐 DESIGNED ONLY.**
- **Milestone 8's train/test split is row-level, not customer-level** —
  see Technical Debt #18 in project-status.md. Deliberately left as-is.
- **Baseline (M7) and ML model (M8) metrics are on different evaluation
  bases** (full dataset vs. held-out test split) — see Technical Debt #19.
  Directionally comparable, not strictly identical.
- **No formal model validation/promotion mechanism exists yet** —
  Milestone 8 registers models to Unity Catalog; it does not promote any
  of them to a production alias. This is explicitly Milestone 9's job.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Every technology must have a stated architectural purpose — no CV-padding.
- Claude Desktop workflow: never assume direct local file/execution access —
  provide files and exact commands, wait for the user to run them and
  report output.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  this is what caught the M6/M7 bugs, and in Milestone 8 it's what caught
  both the `is_anomaly` derivation mistake (design review, before any run)
  and confirmed the label counts (542/26,586) reconciled correctly after
  the fix. Apply this scrutiny to every future feature/metric with an
  implicit "this should equal that" property.
- **Spark/Databricks runtime-global `NameError`s are a confirmed recurring
  risk area** — four independent instances now (`spark` twice, `display`,
  `dbutils`). Check for this proactively in any new notebook.
- **When a genuine tension exists between a real coding-standard rule and
  a real platform constraint** (e.g. `ruff`'s `E402` vs. Databricks'
  mandatory `%pip install` → restart → import sequence), resolve it with a
  narrowly scoped, explained config exception — not a blanket ignore, and
  not by silently working around the platform constraint in a way that
  would break at runtime.
- When something goes wrong, don't chase it indefinitely if the user picks
  a pragmatic resolution — accept and document the trade-off explicitly
  (see M8 Technical Debt #18/#19) rather than silently reopening it later.

## Immediate Next Step
Milestone 8 is fully closed. Next up is **Milestone 9 (model validation and
promotion)** per the approved roadmap — defining a concrete gate (e.g.
minimum `channel_deviation` recall, no precision regression below some
floor relative to the baseline) that a registered model must pass before
being promoted to a production alias, with LogisticRegression v1 as the
first real candidate to run through it. Not started; do not begin without
explicit user confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009-airflow-local-dev-topology.md` — Airflow version/executor decision
- `docs/adr/ADR-010-local-to-databricks-bronze-ingestion.md` — ingestion mechanism,
  Bronze design, and the merchant_category NULL-caveat decision
- `docs/adr/ADR-011-silver-data-quality-strategy.md` — Silver validation mechanism,
  quarantine strategy, and the amount NULL-vs-0.0 technical debt decision
- `docs/adr/ADR-012-gold-feature-engineering-strategy.md` — Gold feature design,
  leakage-boundary convention, amount-applicability rule, empty-window-frame
  NULL semantics, and the deliberate drop of time-of-day deviation
- `docs/adr/ADR-013-baseline-detector-design.md` — baseline scoring design,
  threshold-selection rationale, the two Milestone 7 Spark bugs, and the
  `channel_deviation` structural recall limitation
- `docs/adr/ADR-014-ml-model-training-strategy.md` — ML model design, the
  refined ground-truth boundary, both models' verified results, the
  LogisticRegression-as-leading-candidate decision, and the two Milestone
  8 technical-debt items
- `README.md` — public-facing summary (kept minimal, accurate)