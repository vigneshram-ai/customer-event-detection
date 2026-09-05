# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–9 are **complete and verified** (with one explicitly flagged
partial-verification caveat — see below). Milestone 9 (model validation
and promotion) built a gate that reads Milestone 8's already-logged MLflow
metrics for `ced.models.logistic_regression_detector`'s latest version (no
recomputation), checks three thresholds
(`recall_channel_deviation`/`recall` >= 0.95, `precision` >= 0.90), and on
pass promotes via a Unity Catalog model alias. Since no `champion` existed
before this milestone, the run verified was "no existing champion → direct
promotion" — v1 is now `champion`. A fuller champion/challenger/
previous_champion/archived comparison policy is implemented for future
retrains but its comparison branch has not yet been exercised against live
output (needs a second model version to trigger). Milestone 10
(batch inference) has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 8. Milestone 9 adds no
  new testable Python module (Databricks notebook only), so no CI changes
  expected — not yet confirmed post-commit.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with
  only the temporary smoke-test DAG — deliberately deferred to Milestone 12.
- All Milestone 1–8 artifacts unchanged (see prior snapshot / project-status.md
  for full detail): generators, ingestion, Bronze/Silver/Gold, baseline
  detector, ground-truth loading, LogisticRegression/XGBoost training.
- **New in Milestone 9**: `notebooks/validate_and_promote_model.py` — a
  Databricks notebook, no new `pyproject.toml` dependency (uses
  `mlflow.tracking.MlflowClient`, already available in the Databricks-
  managed MLflow runtime).
- **Databricks side, new state**:
  - `ced.models.logistic_regression_detector` v1 now carries the alias
    `champion` (set via `MlflowClient.set_registered_model_alias`,
    confirmed working on Free Edition — previously unverified, same
    pattern as M8's confirmation that model registration itself worked).
  - `ced.models.xgboost_detector` v1 has no alias — deliberately outside
    this milestone's gate (see ADR-015; XGBoost underperforms
    LogisticRegression on every M8 metric).
  - No other Databricks-side state changed. MLflow experiment
    `/Shared/customer_event_detection_m8` is read by the new notebook, not
    written to.
- `pyproject.toml`, lint/format config, and test suite are all unchanged
  from Milestone 8 (34 tests, `ruff` clean) — Milestone 9 required no new
  dependency, no new `per-file-ignores` entry (no `%pip install` in this
  notebook).

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
  deprecated stage-based promotion. These four alias names are **project-
  defined conventions**, not Unity Catalog built-in concepts; only the
  underlying alias mechanism itself is a UC platform feature.
- **Champion/challenger comparison metric is F1** — a single decisive
  number, already logged, avoiding the need to invent a weighting scheme
  across multiple metrics. Ties favor the incumbent champion (stability
  bias).
- **`challenger` is assigned immediately on gate-pass, before any
  comparison happens** — this is a deliberate correction from an earlier
  draft that assigned it only after losing a comparison, which made the
  alias meaningless (a retrospective loser-label rather than "currently
  under evaluation") and risked a losing version silently overwriting a
  better prior challenger.
- **A version that loses its comparison to champion is tagged `archived`,
  not left as `challenger` indefinitely.** This project implements a
  one-shot batch comparison, not live shadow evaluation — there is no
  honest "still being evaluated" state for a version whose one comparison
  already concluded. Leaving it `challenger` would misrepresent that.
- **`archived` only tags the single most-recently-losing version** — a
  stated limitation (Technical Debt #21), not a defect. Earlier losing
  versions remain in the registry (immutable, queryable by version number)
  but lose the alias once a newer version is archived.
- **XGBoost deliberately excluded from this milestone's gate** — it
  underperforms LogisticRegression on every Milestone 8 metric; gating it
  wouldn't demonstrate a new pattern.
- **Verified result**: first-ever run against `logistic_regression_detector`
  (no prior `champion`) — all three gate checks passed
  (`recall_channel_deviation` 1.0000, `recall` 1.0000, `precision` 0.9879),
  v1 promoted directly to `champion`. Final alias state confirmed:
  `champion -> v1`.
- **Explicitly NOT yet verified**: the champion-vs-challenger comparison
  branch (F1 tie-break, `previous_champion` tagging, `challenger`/
  `archived` handling) has never run against live output, since no prior
  champion existed to compare against. Requires a deliberate second model
  version (e.g. a retrain) to exercise — flagged as a follow-up
  verification step in project-status.md's technical debt, not new
  milestone scope.
- **Design iteration caught three gaps before finalizing** (all resolved,
  not left as debt): (1) an early draft assumed 1:1 run-to-version mapping
  via run-name filtering, which would break on retraining — fixed by
  resolving latest *version* directly; (2) an early draft implemented
  champion-only promotion with no challenger concept at all — fixed by
  adding the F1 comparison; (3) an early draft assigned `challenger` only
  *after* losing, making the alias's real meaning never actually
  represented — fixed by assigning it on gate-pass, before comparison.

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
  it isn't a fitted model.
- **Verified result: LogisticRegression is the leading candidate.**
  Test-split (n=8,139) metrics: precision 0.9879, recall 1.0000, F1 0.9939.
  Recall by type: `new_device` 1.000, `geo_deviation` 1.000, `amount_spike`
  1.000, **`channel_deviation` 1.000** (up from the baseline's 0.000).
  XGBoost also fixes `channel_deviation` (1.000) and modestly improves
  `amount_spike` over the baseline (0.8235 vs. 0.8070), but underperforms
  LR on every metric (precision 0.9581, recall 0.9816, F1 0.9697).
- **Two limitations deliberately left as technical debt**: (18) row-level,
  not customer-level, train/test split — harmless for most anomaly types,
  a genuine gap for `amount_spike`; (19) baseline and ML metrics are on
  different evaluation bases (full dataset vs. held-out test split), not
  strictly like-for-like.
- **Four issues caught and fixed** — `is_anomaly` derivation mistake
  (caught in design review), `F821 dbutils` undefined (fourth recurring
  runtime-global instance), `E402` import-order (scoped per-file-ignore
  for `notebooks/*.py`), `bytes` not seekable in upload script (fixed with
  `io.BytesIO`).

## Key Design Decisions From Milestone 7 (do not silently revisit — full detail in ADR-013)
- Baseline uses additive point-scoring, not OR-logic; `prior_event_count_7d`
  and `time_since_last_event_seconds` excluded from scoring (context-only).
- Thresholds fixed and individually reasoned, never swept against ground
  truth — anti-leakage decision for the baseline's role as an untuned
  reference point.
- Detector runs on Databricks; evaluation runs locally against a CSV
  export.
- `model_version` field name (not `detector_version`) is a deliberate
  contract choice, reused unchanged by the ML model/batch inference.
- Verified result: precision 1.0000, recall 0.7435, F1 0.8529. Recall by
  type: `new_device` 100%, `geo_deviation` 100%, `amount_spike` 80.7%,
  `channel_deviation` 0% (structural, resolved by Milestone 8).
- Two Spark bugs caught and fixed: `array_remove(array, None)` nulling the
  whole array; `spark` runtime global `NameError`.

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
  count features over empty windows.
- Gold has no quarantine/rejects path — row-count mismatch is a bug.

## Key Design Decisions From Milestone 5 (do not silently revisit — full detail in ADR-011)
- Silver validation is plain PySpark, not Great Expectations/Pandera/DLT.
- Quarantine failure handling: every Bronze row lands in exactly one of
  `ced.silver.<table>` or `_rejects`, reconciled on every write.
- `event_timestamp` parsed with an explicitly pinned format.
- `merchant_category` NULL valid for 6 non-monetary event types.
- `amount = 0.0` for non-monetary events accepted as the valid sentinel.
- `.cache()`/`.persist()` unsupported on Free Edition serverless compute.

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models`
- Volumes: `bronze.raw_uploads`, `gold.exports`, `training.raw_labels`
- MLflow: Databricks-managed workspace experiment
  `/Shared/customer_event_detection_m8`
- Model registry aliases (new in Milestone 9):
  `ced.models.logistic_regression_detector` v1 → `champion`;
  `ced.models.xgboost_detector` v1 → no alias
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost` is Databricks-side only, not a `pyproject.toml` dependency.
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
  Technical Debt #18. Deliberately left as-is.
- **Baseline (M7) and ML model (M8) metrics are on different evaluation
  bases** — Technical Debt #19. Directionally comparable, not strictly
  identical.
- **Milestone 9's champion-vs-challenger comparison branch is unverified
  against live output** — Technical Debt #20. Needs a second model
  version to exercise.
- **The `archived` alias only tracks the single most-recent losing
  version** — Technical Debt #21. Earlier losses remain in the registry
  by version number but lose the alias tag.
- **Live/shadow evaluation for champion/challenger doesn't exist** — the
  current implementation is one-shot batch comparison only. 📐 DESIGNED
  as a future extension in ADR-015, not implemented; would require batch
  inference to exist first.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always — including
  distinguishing *which specific code branch* has been exercised, not just
  whether the file as a whole "ran" (see Milestone 9's champion/challenger
  branch caveat).
- Update `docs/project-status.md` after every milestone.
- Every technology must have a stated architectural purpose — no CV-padding.
- Claude Desktop workflow: never assume direct local file/execution access —
  provide files and exact commands, wait for the user to run them and
  report output.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  in Milestone 9 this meant catching, during design review before any
  code was finalized, that an early draft's `challenger` semantics were
  backwards (assigned after losing, not before comparing) and that
  champion-only promotion silently dropped a standard MLOps pattern —
  both caught by the user, not by Claude, before implementation.
- **Spark/Databricks runtime-global `NameError`s are a confirmed recurring
  risk area** — four independent instances (`spark` twice, `display`,
  `dbutils`). Check for this proactively in any new notebook. (Milestone 9
  had none — no Spark session used, `MlflowClient` only.)
- **When a genuine tension exists between a real coding-standard rule and
  a real platform constraint**, resolve it with a narrowly scoped,
  explained config exception — not a blanket ignore.
- When something goes wrong, don't chase it indefinitely if the user picks
  a pragmatic resolution — accept and document the trade-off explicitly
  rather than silently reopening it later.
- **Design proposals should be treated as genuinely open to challenge, not
  rubber-stamped** — Milestone 9's final design differs materially from
  Claude's first two drafts, specifically because the user pushed back on
  real gaps (version-vs-run assumption, missing challenger concept,
  backwards challenger-assignment timing) rather than accepting the first
  answer.

## Immediate Next Step
Milestone 9 is closed for `logistic_regression_detector` (gate + direct
champion promotion verified). Next up is **Milestone 10 (batch inference)**
per the approved roadmap — a batch scoring process that loads
`ced.models.logistic_regression_detector@champion` (by alias, never a
hardcoded version, so that Milestone 9's promotion/rollback mechanism
actually has a consumer), scores new customer events, and writes detection
results in the `model_version`-tagged contract format established since
Milestone 7. Not started — do not begin without explicit user confirmation.

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
- `docs/adr/ADR-015-model-validation-and-promotion.md` — validation gate
  thresholds and rationale, alias-based promotion mechanism, champion/
  challenger/previous_champion/archived semantics, the F1 comparison
  decision, and the stated verification/limitation caveats
- `README.md` — public-facing summary (kept minimal, accurate)