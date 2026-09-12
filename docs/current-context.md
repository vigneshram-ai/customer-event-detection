# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–10 are **complete and verified** (with two explicitly
flagged partial-verification caveats — see below). Milestone 10 (batch
inference) built a notebook that loads
`ced.models.logistic_regression_detector@champion` via
`mlflow.pyfunc.load_model`, resolves the alias to a concrete version
number, scores a reproducible sample of existing Gold data, and writes
results to a new `ced.inference.detection_results` table in the
established `model_version`-tagged contract format. Milestone 11
(monitoring, per the roadmap ordering) has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 10.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with
  only the temporary smoke-test DAG — deliberately deferred to Milestone 12.
- All Milestone 1–9 artifacts unchanged (see prior snapshot /
  project-status.md for full detail): generators, ingestion,
  Bronze/Silver/Gold, baseline detector, ground-truth loading,
  LogisticRegression/XGBoost training, validation gate and
  alias-based promotion.
- **New in Milestone 10**: `notebooks/batch_inference.py` — a Databricks
  notebook, no new `pyproject.toml` dependency (uses `mlflow`,
  `mlflow.tracking.MlflowClient`, and PySpark, all already available in
  the Databricks-managed runtime).
- **Databricks side, new state**:
  - New schema `ced.inference` created.
  - New table `ced.inference.detection_results` — 500 rows, written via
    `mode("overwrite")`. 12 rows flagged (`detection_flag = true`,
    2.40%), consistent with Milestone 3's ~2% anomaly injection rate.
  - `model_version` column value: inferred as
    `logistic_regression_detector_v1` from known registry state (only
    v1 exists, no retrain since Milestone 9) — the pasted terminal
    output truncated this column, so this was **not directly observed**;
    flagged rather than silently assumed (Technical Debt #26).
  - No other Databricks-side state changed. `ced.models.*` aliases
    unchanged from Milestone 9. `ced.training` was not read by this
    milestone's notebook (only referenced conceptually in design
    discussion, then deliberately avoided — see decisions below).
- `pyproject.toml`, lint/format config, and test suite are all unchanged
  from Milestone 8 (34 tests, `ruff` clean) — Milestone 10 required no
  new dependency, no new `per-file-ignores` entry.

## Key Design Decisions From Milestone 10 (do not silently revisit — full detail in ADR-016)
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
  the authoritative performance numbers.
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
- **A design trade-off was raised and explicitly resolved**: since the
  fixed 0.5 threshold happens to equal sklearn's own default
  classification boundary, generic `pyfunc.predict()` alone would return
  an identical class label without any unwrapping. This was rejected as
  the implementation approach — `detection_score` is a required contract
  field (per the original project scope), and relying on the coincidence
  would silently couple the threshold decision to an implicit library
  default rather than an explicit, adjustable value in this pipeline. It
  would also forfeit the continuous score needed for future monitoring
  (severity ranking, score-distribution drift).
- **A real bug was caught and fixed via reading actual code, not
  guessing**: `predict_proba` initially raised
  `ValueError: Input X contains NaN`, traced to amount-based Gold
  features being structurally NULL for non-monetary rows (ADR-012). The
  fix was to read `train_model.py`'s actual preprocessing and replicate
  it exactly (`fillna(0)` on `FEATURE_COLS`) rather than choosing an
  independent imputation strategy — an inference-time imputation that
  didn't match training would be a silent train/serve-skew bug, worse
  than any single imputation choice.
- **The `fillna(0)` choice was reviewed for semantic correctness, not
  just replicated blindly.** It collapses two distinct NULL causes
  (current-row event is non-monetary, vs. a monetary row with no prior
  monetary history) into the same encoded value. Judged safe for this
  dataset specifically: the synthetic generator never produces a
  genuinely monetary event with `amount = 0.0` (reserved as the ADR-011
  non-monetary sentinel), so a real prior-amount average of exactly 0
  cannot occur — meaning `0` unambiguously signals "no relevant monetary
  history" either way. The two causes remain structurally
  indistinguishable in the encoded features (Technical Debt #25), but
  this is not judged likely to mislead the model given the actual data.
- **`model_version` is resolved to a concrete version number at scoring
  time** (e.g. `logistic_regression_detector_v1`), not written as the
  alias `champion` — so historical detection records stay correctly
  attributed even if `champion` later moves to a different version.
  Resolved via `MlflowClient.get_model_version_by_alias`.
- **Output written to a new `ced.inference` schema**,
  `detection_results` table, with `mode("overwrite")` — each run
  represents "the current batch scored." No append/dedup-by-`event_id`
  strategy exists yet for accumulating multiple historical batches
  (Technical Debt #24) — a real future need once genuinely
  repeated/incremental batches exist.
- **Verified result**: 500 rows scored, 12 flagged (2.40%) — consistent
  with Milestone 3's ~2% anomaly injection rate, treated as a genuine
  sanity check rather than just confirming the notebook ran without
  error. CI confirmed green.
- **Explicitly NOT fully verified**: the exact `model_version` string
  written (`logistic_regression_detector_v1`) was inferred from known
  registry state, not literally observed in the pasted terminal output
  (column was truncated in the `groupBy` display). Low risk given only
  one version currently registered, but stated rather than silently
  treated as confirmed (Technical Debt #26).

## Key Design Decisions From Milestone 9 (do not silently revisit — full detail in ADR-015)
- **Gate reads already-logged metrics only — never recomputes.** The
  notebook resolves the *latest* registered version of
  `logistic_regression_detector` dynamically via `search_model_versions`
  (not a hardcoded run name or version number), so it stays correct across
  future retrains without code changes.
- **Three gate thresholds**: `recall_channel_deviation >= 0.95`,
  `recall >= 0.95`, `precision >= 0.90`. The precision floor is
  deliberately below the M7 baseline's 1.0000 — baseline and ML metrics
  are on different evaluation bases (Technical Debt #19: full dataset vs.
  held-out test split), so requiring an exact match would compare
  incomparable numbers.
- **Promotion is alias-based** (`champion`/`challenger`/
  `previous_champion`/`archived`), not stage-based — Unity Catalog
  deprecated stage-based promotion. These four alias names are
  **project-defined conventions**, not Unity Catalog built-in concepts.
- **Champion/challenger comparison metric is F1** — a single decisive
  number, already logged. Ties favor the incumbent champion (stability
  bias).
- **`challenger` is assigned immediately on gate-pass, before any
  comparison happens** — this is a deliberate correction from an earlier
  draft that assigned it only after losing a comparison, which made the
  alias meaningless.
- **A version that loses its comparison to champion is tagged `archived`,
  not left as `challenger` indefinitely.** This project implements a
  one-shot batch comparison, not live shadow evaluation.
- **`archived` only tags the single most-recently-losing version** —
  a stated limitation (Technical Debt #21), not a defect.
- **XGBoost deliberately excluded from this milestone's gate** — it
  underperforms LogisticRegression on every Milestone 8 metric.
- **Verified result**: first-ever run against `logistic_regression_detector`
  (no prior `champion`) — all three gate checks passed
  (`recall_channel_deviation` 1.0000, `recall` 1.0000, `precision` 0.9879),
  v1 promoted directly to `champion`. Final alias state confirmed:
  `champion -> v1`.
- **Explicitly NOT yet verified**: the champion-vs-challenger comparison
  branch has never run against live output, since no prior champion
  existed to compare against. Requires a deliberate second model version
  to exercise (Technical Debt #20).

## Key Design Decisions From Milestone 8 (do not silently revisit — full detail in ADR-014)
- **Ground-truth boundary refined, not discarded.** Ground truth may
  enter Databricks **for training only**, into an isolated schema
  (`ced.training`) that inference paths never read. **`ced.training`
  must never be read by any future batch-inference process** — this
  boundary held through Milestone 10; the batch-inference design
  discussion explicitly considered and rejected an approach that would
  have required reading it.
- **The feature/label join is never persisted.** `train_model.py` joins
  Gold features and training labels **in-memory only** — no table
  anywhere contains both together. This is *why* Milestone 10 could not
  simply reconstruct the exact M8 test split without a bootstrap script;
  documented as a deliberate consequence, not an oversight.
- **Registered models live in `ced.models`, deliberately separate from
  `ced.training`.**
- **Both LogisticRegression and XGBoost were trained**, on all 8 Gold
  features. Stratified 70/30 split by `anomaly_type`, seed 42,
  `fillna(0)` on `FEATURE_COLS` before fitting — this exact preprocessing
  step is what Milestone 10 had to discover and replicate for
  train/serve parity.
- **Verified result: LogisticRegression is the leading candidate.**
  Test-split (n=8,139) metrics: precision 0.9879, recall 1.0000, F1 0.9939.
- **Two limitations deliberately left as technical debt**: (18) row-level,
  not customer-level, train/test split; (19) baseline and ML metrics are
  on different evaluation bases.

## Key Design Decisions From Milestone 7 (do not silently revisit — full detail in ADR-013)
- Baseline uses additive point-scoring, not OR-logic.
- Thresholds fixed and individually reasoned, never swept against ground
  truth.
- `model_version` field name (not `detector_version`) is a deliberate
  contract choice, reused unchanged by the ML model and, now, batch
  inference (Milestone 10) — confirming the contract has held across
  three milestones.
- Verified result: precision 1.0000, recall 0.7435, F1 0.8529.

## Key Design Decisions From Milestone 6 (do not silently revisit — full detail in ADR-012)
- Gold table is event-grain, one row per Silver event.
- Leakage boundary: every window feature's `rowsBetween`/`rangeBetween`
  ends at `-1` relative to the current row — non-negotiable.
- Eight features shipped: `prior_event_count_7d`, `prior_avg_amount_90d`,
  `amount_deviation_from_prior_avg`, `is_new_device`, `is_unusual_channel`,
  `is_unusual_country`, `prior_failed_login_count_24h`,
  `time_since_last_event_seconds`.
- Amount-based features are NULL for non-monetary current-row event
  types — this exact behavior is what Milestone 10 had to handle at
  inference time via `fillna(0)`, matching training.

## Key Design Decisions From Milestone 5 (do not silently revisit — full detail in ADR-011)
- Silver validation is plain PySpark, not Great Expectations/Pandera/DLT.
- Quarantine failure handling.
- `amount = 0.0` for non-monetary events accepted as the valid sentinel
  — this decision is what made Milestone 10's `fillna(0)` review
  possible (a real monetary average of exactly 0 cannot occur, so 0 is
  an unambiguous "no history" signal).

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models`, `inference` (new in Milestone 10)
- Volumes: `bronze.raw_uploads`, `gold.exports`, `training.raw_labels`
- MLflow: Databricks-managed workspace experiment
  `/Shared/customer_event_detection_m8`
- Model registry aliases: `ced.models.logistic_regression_detector` v1 →
  `champion`; `ced.models.xgboost_detector` v1 → no alias (unchanged
  since Milestone 9)
- `ced.inference.detection_results`: 500 rows, 12 flagged, new in
  Milestone 10
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost` and `mlflow` are Databricks-side only, not `pyproject.toml`
  dependencies.
- PAT stored in `.env` (git-ignored)

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written.
- Time-of-day deviation — designed and partially implemented, then
  removed.
- `amount = 0.0` ambiguity — intentionally left as-is at Silver, resolved
  at Gold; a related ambiguity now also documented for Milestone 10's
  `fillna(0)` at inference (Technical Debt #25).
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
  DESIGNED as a future extension in ADR-015; batch inference now exists
  (Milestone 10) as a prerequisite, but shadow evaluation itself is not
  implemented.
- **Milestone 10's batch is a sample of existing Gold data, not
  genuinely new/unseen events** — Technical Debt #22. Mechanism-level
  demonstration only; not a fresh performance measurement.
- **`predict_proba` extraction via sklearn-specific unwrap, not a
  flavor-agnostic pattern** — Technical Debt #23.
- **`ced.inference.detection_results` uses `overwrite`, no historical
  accumulation** — Technical Debt #24.
- **`fillna(0)` collapses two distinct NULL causes in amount-based
  features** — Technical Debt #25. Judged safe for this dataset, not
  structurally resolved.
- **Milestone 10's exact `model_version` output string was inferred, not
  directly observed** — Technical Debt #26.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always —
  including *which specific code branch* has been exercised.
- Update `docs/project-status.md` after every milestone.
- Every technology must have a stated architectural purpose — no CV-padding.
- Claude Desktop workflow: never assume direct local file/execution access —
  provide files and exact commands, wait for the user to run them and
  report output.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  Milestone 10's 2.40% flagged rate against M3's ~2% injection rate is
  the latest instance of this pattern; the notebook running without
  error was not itself treated as sufficient verification.
- **When implementation reveals a preprocessing dependency between
  stages (e.g. inference needing training's exact `fillna` logic), go
  read the actual upstream code rather than choosing an independent
  approach** — Milestone 10's NaN bug was resolved this way, consistent
  with the "read actual state, don't assume it" pattern established
  since Milestone 6.
- **Spark/Databricks runtime-global `NameError`s are a confirmed
  recurring risk area** — four independent instances through Milestone
  8. None recurred in Milestones 9 or 10 (no raw Spark session
  manipulation requiring `dbutils`/`display` in either notebook).
- **Design proposals should be treated as genuinely open to challenge,
  not rubber-stamped** — Milestone 10's design went through three rounds
  of user-driven revision (new-data-generation approach → sample-based
  approach; `sklearn.load_model` → `pyfunc.load_model` with unwrap;
  challenging whether `detection_score` was even needed given the 0.5
  threshold) before implementation, each resolving a real design
  question rather than being accepted on the first pass.

## Immediate Next Step
Milestone 10 is closed. Next up is **Milestone 11** per the approved
roadmap (monitoring, per the roadmap ordering: batch inference →
monitoring → security → full CI/CD → Airflow orchestration at Milestone
12). Not yet scoped in detail — do not begin without explicit user
confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009-airflow-local-dev-topology.md` — Airflow version/executor decision
- `docs/adr/ADR-010-local-to-databricks-bronze-ingestion.md` — ingestion mechanism,
  Bronze design, and the merchant_category NULL-caveat decision
- `docs/adr/ADR-011-silver-data-quality-strategy.md` — Silver validation mechanism,
  quarantine strategy, and the amount NULL-vs-0.0 technical debt decision
- `docs/adr/ADR-012-gold-feature-engineering-strategy.md` — Gold feature design,
  leakage-boundary convention, amount-applicability rule
- `docs/adr/ADR-013-baseline-detector-design.md` — baseline scoring design,
  threshold-selection rationale, the `model_version` contract origin
- `docs/adr/ADR-014-ml-model-training-strategy.md` — ML model design, the
  refined ground-truth boundary, both models' verified results
- `docs/adr/ADR-015-model-validation-and-promotion.md` — validation gate
  thresholds and rationale, alias-based promotion mechanism
- `docs/adr/ADR-016-batch-inference-design.md` — batch-sourcing trade-off
  (sample vs. new data vs. exact test split), `pyfunc` load + unwrap
  rationale, `detection_score`-vs-threshold-coincidence decision,
  `fillna(0)` train/serve-parity reasoning, `ced.inference` schema/
  write-mode decisions
- `README.md` — public-facing summary (kept minimal, accurate)