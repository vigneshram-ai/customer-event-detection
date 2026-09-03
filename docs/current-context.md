# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–7 are **complete and verified**. Milestone 7 (baseline
rule-based detector) is fully closed — real end-to-end run against live
Databricks confirmed, evaluated against Milestone 3 ground-truth anomaly
labels for the first time in this project (precision 1.0, recall 0.7435, F1
0.8529), lint/format clean, CI green. Two implementation bugs were caught and
fixed during verification (see below and ADR-013). A structural, by-design
recall gap on `channel_deviation` anomalies (0%) was identified and
deliberately left untuned — documented as a named motivator for Milestone 8,
not a defect. Milestone 8 has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 7.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with only the
  temporary smoke-test DAG. Not orchestrating anything real yet — deliberately
  deferred to Milestone 12.
- `data_generation/customer_generator.py`, `data_generation/event_generator.py`,
  `ingestion/upload_to_volume.py` all exist, are tested (31 tests total, all
  passing), `ruff` clean.
- `notebooks/bronze_ingestion.py`, `notebooks/silver_transformation.py`,
  `notebooks/gold_feature_engineering.py`, and `notebooks/baseline_detector.py`
  all exist and have been run successfully against the live Databricks Free
  Edition workspace. **None has automated test coverage** — verification is
  manual/observed-output only (no local PySpark harness in this project).
- `evaluation/evaluate_baseline.py` exists, runs locally (not on Databricks),
  and has been run successfully against real downloaded data. No automated
  test coverage yet (technical debt #17).
- **Databricks side is real and verified**: workspace
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`, Unity Catalog `ced`.
  - `ced.bronze.customers` (1,000 rows), `ced.bronze.events` (27,128 rows)
  - `ced.silver.customers` (1,000 valid, 0 rejects), `ced.silver.events`
    (27,128 valid, 0 rejects)
  - `ced.gold.customer_events_features` (27,128 rows, exact 1:1 reconciliation
    with `ced.silver.events`, 8 features — no quarantine/rejects path at Gold,
    a row-count mismatch here would indicate a bug, not a data-quality failure)
  - `ced.gold.baseline_detections` (27,128 rows, new in Milestone 7 — exact
    1:1 reconciliation with the Gold features table, no quarantine path)
  - Volume `ced.bronze.raw_uploads` holds `customers.csv`, `events.csv` — NOT the
    ground-truth sidecar, deliberately excluded.
  - Volume `ced.gold.exports` (new in Milestone 7) holds a flattened CSV
    export of `baseline_detections`, downloaded locally for evaluation.
- Compute is **serverless only** (Free Edition) — `.persist()`/`.cache()` are
  unsupported (`NOT_SUPPORTED_WITH_SERVERLESS`).
- No MLflow, no trained ML model exist yet. A rule-based baseline detector
  does exist and is verified (Milestone 7) — do not conflate the two.
- `pyproject.toml` has three production dependencies: `databricks-sdk`,
  `python-dotenv` (since Milestone 4), and `pandas` (added Milestone 7).
- `.env` (git-ignored, confirmed via `git status`) holds `DATABRICKS_HOST` /
  `DATABRICKS_TOKEN`. Never commit this file or its contents.

## Key Design Decisions From Milestone 7 (do not silently revisit — full detail in ADR-013)
- **Baseline uses additive point-scoring, not OR-logic**: each of 7 rules
  across 5 of the 8 Gold features contributes fixed points; `detection_flag`
  triggers at `detection_score >= 2`. `prior_event_count_7d` and
  `time_since_last_event_seconds` are deliberately excluded from scoring
  (no principled global threshold without a customer-relative baseline) and
  carried as context-only columns.
- **Thresholds are fixed and individually reasoned, never swept against
  ground truth** — a deliberate anti-leakage decision for a component whose
  entire purpose is being an untuned reference point.
- **Detector runs on Databricks; evaluation runs locally.**
  `notebooks/baseline_detector.py` writes `ced.gold.baseline_detections` and
  exports a flattened CSV to a new volume, `ced.gold.exports`.
  `evaluation/evaluate_baseline.py` (local, first use of `pandas` in this
  project) downloads it and joins against `data/raw/events_ground_truth.csv`.
  Ground truth is deliberately never uploaded to the warehouse — same
  boundary established in ADR-010's Bronze-upload exclusion.
- **`model_version` field name (not `detector_version`) is a deliberate
  contract choice** — the baseline's output schema
  (`customer_id, event_id, event_timestamp, detection_score, detection_flag,
  reason, model_version, scored_at`) is meant to be reused unchanged by the
  eventual MLflow-registered model and batch inference.
- **Verified result**: precision 1.0000 (0 false positives across 27,128
  events), recall 0.7435 (403/542 injected anomalies caught), F1 0.8529.
  Recall by type: `new_device` 100%, `geo_deviation` 100%, `amount_spike`
  80.7%, `channel_deviation` **0%** (structural — see below).
- **`channel_deviation` 0% recall is a deliberate, documented limitation, not
  a bug and not retuned.** `is_unusual_channel` correctly fires on all 128
  such anomalies but is worth only 1 point against a 2-point flag threshold,
  and never co-occurs with another signal in this dataset (consistent with
  the M3 generator's single-event-level anomaly injection). Raising its
  weight after seeing this result would be tuning against ground truth —
  explicitly rejected. **Named as the concrete motivator for Milestone 8**:
  the ML model should be evaluated in part on whether it can recover this
  recall without hand-tuned thresholds.
- **`prior_failed_login_count_24h` rules never fired** — no injected
  login-burst anomaly type exists in current ground truth (technical debt
  #5). Rule is architecturally sound but currently unverified against any
  known-anomalous case.
- **Two Spark bugs caught during live verification, both fixed** (full detail
  in ADR-013):
  1. `F.array_remove(array, None)` nulled the entire `reason` array on every
     row — Spark's null-value-removal semantics, not a null-filter. Fixed
     with `F.filter(array, lambda x: x.isNotNull())`.
  2. `NameError: spark is not defined` — same root cause as the Milestone 4
     Bronze fix, now a **confirmed recurring pattern** in this project (two
     independent instances). Fixed with
     `from databricks.sdk.runtime import spark`. **Check for this
     proactively in any new notebook going forward.**

## Key Design Decisions From Milestone 6 (do not silently revisit — full detail in ADR-012)
- **Gold table is event-grain**, one row per Silver event — not a daily/customer
  aggregate — because the eventual batch-inference output spec
  (`customer_id`, `event_id`, `detection_score`, ...) is per-event.
- **Leakage boundary enforced on every window feature**: all `rowsBetween`/
  `rangeBetween` windows end at `-1` relative to the current row. No feature
  ever uses the current event or any future event. Treated as non-negotiable.
- **Eight features shipped**: `prior_event_count_7d` (7-day rolling count),
  `prior_avg_amount_90d` (90-day rolling avg, monetary events only),
  `amount_deviation_from_prior_avg` (monetary events only), `is_new_device`,
  `is_unusual_channel`, `is_unusual_country` (country-mismatch proxy, not true
  geo-distance — no lat/long in the data model), `prior_failed_login_count_24h`
  (24h rolling count, applies to every row regardless of current event type),
  `time_since_last_event_seconds`.
- **Time-of-day deviation was designed and partially implemented, then
  deliberately dropped** before final verification — the circular-statistics
  approach (hour-angle via `sin`/`cos`, circular mean via `atan2`, wrapped
  angular distance) is fully specified in ADR-012 and ready to pick up later,
  but was cut because the complexity wasn't justified without a concrete
  downstream need driving it. Do not describe this feature as implemented.
- **Amount-feature applicability rule (bug #1, fixed)**: `prior_avg_amount_90d`
  and `amount_deviation_from_prior_avg` are `NULL` whenever the *current row's*
  `event_type` is not monetary — regardless of the customer's event history.
  The first implementation only gated the rolling window's *input* on event
  type but not the *emitted value*, so non-monetary events got a real number
  instead of `NULL`. Caught by inspecting live sanity-check output (non-monetary
  null counts didn't equal row counts) and fixed before closing the milestone.
- **This resolves the ADR-011 `amount = 0.0` ambiguity at the feature layer**:
  even though Silver still can't distinguish "not applicable" from "genuinely
  zero" for `amount` on non-monetary events, Gold's amount-based features are
  `NULL` for all non-monetary events regardless — the ambiguity does not
  propagate downstream into features a future model would consume.
- **Empty-window-frame NULL rule (bug #2, fixed)**: Spark's `SUM` (and other
  aggregates) over an **empty window frame** returns `NULL`, not the aggregate's
  identity value (`0` for `SUM`) — a general Spark behavior, not specific to
  this dataset. `prior_failed_login_count_24h` initially returned `NULL` for
  19,062 of 27,128 rows (~70%, wherever a customer had no failed-login history
  in the preceding 24h) instead of the correct `0`. Caught the same way — the
  sanity check expected `0` nulls and got 19,062. **Fixed** with
  `F.coalesce(..., F.lit(0))`. **This pattern recurred in Milestone 7 in a
  different form (the `array_remove` null-semantics bug) — Spark null
  semantics are a recurring risk area for this project, not a one-off.**
- **`is_new_device` treats `normal_device` as known from event zero**: `False`
  if the device matches the customer's declared `normal_device` OR appears in
  prior event history; `True` only if neither. Explicit user correction to the
  initial events-only-history proposal.
- **Gold has no quarantine/rejects path**, unlike Silver. A row-count mismatch
  between Silver input and Gold output is treated as a bug (e.g. join fan-out)
  and raises immediately. The same convention was carried into the Milestone 7
  baseline detector.
- **Verification scope note**: Milestone 6 verification is limited to structural
  sanity checks (row-count reconciliation, null-count patterns matching the
  applicability rules, plausible true/false counts for boolean indicators). The
  Gold features had **not** been cross-referenced against
  `events_ground_truth.csv` (the Milestone 3 anomaly labels) for correctness
  as of Milestone 6's close. **This gap was closed in Milestone 7** via the
  baseline detector's evaluation step — see above.
- **Both Milestone 6 bugs caught during live verification, not code review** —
  both by reading actual sanity-check numbers and noticing they contradicted
  the stated design, not by the notebook erroring. This is the pattern to
  keep applying: numbers must be read and reasoned about, not just confirmed
  as "ran without error." **Confirmed again in Milestone 7** (the empty
  `reason` breakdown table was the tell, not an error).

## Key Design Decisions From Milestone 5 (do not silently revisit — full detail in ADR-011)
- Silver validation logic is plain PySpark, not Great Expectations/Pandera/DLT.
- Failure handling is quarantine: every Bronze row lands in exactly one of
  `ced.silver.<table>` or `ced.silver.<table>_rejects`, reconciled on every write.
- Customers validated and split before events; events' referential-integrity
  check uses the cleaned Silver `customers` set, not raw Bronze.
- `event_timestamp` parsed using an explicitly pinned format
  (`yyyy-MM-dd'T'HH:mm:ss`), not `to_timestamp()` auto-detection.
- `merchant_category` NULL caveat from ADR-010 resolved: NULL valid for 6
  non-monetary event types, flagged only on monetary types.
- **`amount = 0.0` for non-monetary events accepted as the valid sentinel** at
  Silver — deliberately not "fixed" by touching `event_generator.py`. Full
  rationale in ADR-011. (See Milestone 6 notes above for how this is handled
  at the Gold feature layer.)
- `.cache()`/`.persist()` not available on Databricks Free Edition serverless
  compute — removed from `silver_transformation.py`.

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, and `gold`,
  volumes `bronze.raw_uploads` and `gold.exports` (new in Milestone 7)
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas` (added
  Milestone 7)
- PAT stored in `.env` (git-ignored)

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written.
- Time-of-day deviation — designed and partially implemented, then removed.
  If revisited, treat as a fresh design-implement-verify cycle, reusing the
  ADR-012 design rather than resurrecting removed code without re-checking it.
- `amount = 0.0` ambiguity at Silver — intentionally left as-is at that layer;
  resolved at the Gold feature layer (NULL for non-monetary amount features)
  rather than at the source.
- Bronze, Silver, and Gold processing are all manual (no Airflow orchestration)
  — deliberate, per ADR-010/ADR-011/ADR-012, until Milestone 12.
- `channel_deviation` anomalies are structurally unreachable by the
  Milestone 7 baseline (0% recall) — deliberate, documented, not to be
  "fixed" by retuning baseline weights against ground truth. Relevant context
  for Milestone 8's ML model evaluation.
- `prior_failed_login_count_24h` baseline rules have zero support in current
  ground truth — no login-burst anomaly type in the generator.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and verified
  with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Every technology must have a stated architectural purpose — no CV-padding.
- Claude Desktop workflow: never assume direct local file/execution access —
  provide files and exact commands, wait for the user to run them and report
  output.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  Milestone 6 caught two real bugs (amount-applicability gating, empty-window
  NULL semantics), and Milestone 7 caught a third (null `reason` array),
  purely because sanity-check numbers or table outputs were read and
  questioned when they didn't match the stated design, not because anything
  errored. Apply this scrutiny going forward, especially for any future
  feature/metric that has an implicit "this should equal that" property.
- **Spark null semantics are a recurring risk area for this project** — three
  independent instances now (empty-window `SUM` returning NULL,
  `array_remove` nulling the whole array on a NULL removal-value, and the
  `spark`-runtime-global `NameError`, twice). Treat any new Spark
  transformation involving aggregates, arrays, or notebook runtime globals
  with proactive suspicion, not just reactive debugging.
- When something goes wrong (e.g. the `amount = 0.0` investigation, or the
  Milestone 6/7 fixes), don't chase it indefinitely if the user picks a
  pragmatic resolution — accept and document the trade-off explicitly rather
  than silently reopening it later.

## Immediate Next Step
Milestone 7 is fully closed. Next up is **Milestone 8 (ML model)** per the
approved 23-milestone roadmap — likely Isolation Forest, Logistic Regression,
or XGBoost per the project's stated ML scope (section 9), evaluated against
the Milestone 7 baseline (precision 1.0, recall 0.7435, F1 0.8529) as the
reference point to beat. Not started; do not begin without explicit user
confirmation.

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
- `README.md` — public-facing summary (kept minimal, accurate)