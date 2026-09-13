# ADR-017: Monitoring Strategy — Evidently-Based Data Drift and Data Quality

## Context

Milestone 11, per the approved roadmap (batch inference → monitoring → security →
full CI/CD → Airflow orchestration at Milestone 12). Two constraints shaped this
milestone from the start:

- Airflow orchestration is deliberately deferred to Milestone 12 — there is no
  orchestrated pipeline yet to attach pipeline-level (task success/duration/retry)
  monitoring to.
- Milestone 10's batch inference scored a reproducible *sample of existing Gold
  data* (Technical Debt #22), not genuinely new/unseen events, and
  `ced.inference.detection_results` was written with `mode("overwrite")`
  (Technical Debt #24) with no further inference runs planned.

The user explicitly directed that Milestone 10's batch be treated as if it were a
genuinely new/incoming batch for the purposes of this milestone, on the basis that
the sample-vs-new-data choice was a data-generation convenience, not a limitation
worth re-litigating here. This ADR records the resulting design.

## Problem

What should Milestone 11 monitor, using what tooling, computed how, against what
reference, persisted in what form — given a single available "current" batch, no
orchestration layer, and no ground-truth labels available at inference time?

## Options Considered

**1. Custom hand-rolled statistics (PSI, quantile stats) vs. Evidently.**
An initial design used self-computed PSI and quality checks, explicitly avoiding
Evidently to sidestep dependency on its internal JSON schema. Rejected per
explicit user direction: Evidently is a recognized, real open-source tool: using it
directly is more valuable for this project's purpose than a hand-rolled equivalent,
and the schema-fragility risk was judged acceptable with a defensive fallback (see
Consequences).

**2. Forced PSI (`method="psi"`) vs. Evidently's auto-selected per-column test.**
Initial reasoning: force PSI on every column for a single, comparable scale across
features. This reasoning was reviewed against a real Evidently sample output and
found incorrect — auto-selected tests (Wasserstein distance for numerical columns,
Jensen-Shannon distance for categorical columns in this run) already roll up into a
calibrated per-column Drifted/Not-Drifted boolean and an aggregate dataset-level
drift share, which is what actually provides cross-feature comparability. Forcing
PSI would have overridden Evidently's own calibrated defaults for no real benefit.
**Decision: auto-select (Evidently's default).** PSI's specific relevance to
banking/credit-risk model monitoring is retained as documented domain context, not
as the implemented method.

**3. What counts as "current" data.**
Per explicit user direction, `ced.inference.detection_results` (Milestone 10's
500-row batch) is treated as the batch under monitoring. Documented consequence:
because this batch is a subset of the reference population it's compared against,
near-zero drift is the *expected, correct* outcome — a negative control confirming
the mechanism works — not a genuine "checked for drift in production and found
none" result.

**4. Reference/current feature-imputation parity.**
While implementing the null-safety check, discovered that
`ced.inference.detection_results`'s persisted `FEATURE_COLUMNS` are **raw
(non-imputed) Gold values**, not the `fillna(0)`-imputed values actually fed to the
model at scoring time. Milestone 10's `fillna(0)` fix (ADR-016) was applied to the
transient scoring matrix only and was never propagated to the output write. This
corrects an inaccurate claim in ADR-016 / `current-context.md` (Milestone 10
section) that the persisted features were already imputed. **Decision:** apply
`fillna(0)` identically to both reference and current feature sets inside the
monitoring notebook (replicating `train_model.py`'s exact preprocessing), rather
than assuming either side was pre-imputed.

**5. How to persist Evidently's structured output.**
Initial implementation avoided hard-coding Evidently's internal `report.dict()`
schema, using a generic best-effort extraction with a raw-JSON fallback. Real
output showed the assumed field names (`metric_id` as a readable name) were wrong —
the actual schema uses `id` (hash) + `metric_name` (human-readable) per metric, with
tests linked back via `test["metric_config"]["metric_id"]` and a `description` field
stating the measured value against its threshold in plain language. **Decision:**
rewrite extraction against the confirmed real schema, keep the raw-JSON fallback for
resilience against future Evidently schema changes.

## Decision

- **Data Drift Report**: Evidently `Report([DataDriftPreset()], include_tests="True")`,
  current (`ced.inference.detection_results`) vs. reference
  (`ced.gold.customer_events_features`), over the 8 Gold features. Column types
  declared explicitly via `DataDefinition` (binary flags as categorical) so 0/1
  flags aren't treated as continuous numerics.
- **Data Summary Report**: Evidently `Report([DataSummaryPreset()], include_tests="True")`,
  standalone on the current batch (8 features + `detection_score` +
  `detection_flag`, 10 columns). No reference comparison for the two prediction
  columns — no prior scored batch exists, so these are descriptive snapshot stats,
  not drift metrics.
- Both reports saved as interactive HTML, rendered inline via `displayHTML`.
- Structured results flattened into a new append-mode table,
  `ced.monitoring.batch_quality_report` (`run_id`, `scored_at`, `metric_category`,
  `metric_name`, `value`, `threshold` [the test's plain-language description],
  `status`).

## Rationale

Using Evidently directly (rather than a custom equivalent) is the more credible,
interview-recognizable choice, and the auto-selected per-column tests are both
statistically better-suited to mixed continuous/categorical features and already
solve the cross-feature comparability problem that motivated the (rejected) PSI-
forcing approach. Treating Milestone 10's batch as "current," while honestly
documenting why near-zero drift is expected rather than a genuine finding, lets the
mechanism be fully exercised without overclaiming what it proved.

## Verified Result

Two independent notebook runs (distinct `run_id`s), each writing 79 metric rows (9
drift + 70 data-quality/summary) to `ced.monitoring.batch_quality_report` — 158
rows total. All metric values identical across both runs, confirming deterministic
computation and correct `append`-mode accumulation across multiple runs (an
unplanned but genuine verification of the recurrence design, beyond this
milestone's original scope).

- **Drift**: `DriftedColumnsCount` share = 0.0 (0 of 8 features drifted). Per-column
  `ValueDrift` scores ranged ~0.006–0.064, all under the 0.1 threshold, all
  `TestStatus.SUCCESS`.
- **Data quality**: of the tested subset, all passed except two, both interpreted
  as expected/benign rather than defects:
  - `DuplicatedRowCount() = 18` → FAIL. Checked columns exclude identifiers
    (`event_id`/`customer_id`); several features are sparse/low-cardinality, so
    distinct events sharing an identical feature vector is expected.
  - `AlmostConstantColumnsCount() = 5` → FAIL. The 5 columns
    (`is_new_device`, `is_unusual_channel`, `is_unusual_country`, `detection_flag`,
    `prior_failed_login_count_24h`) are rare-event indicators by design; low
    prevalence is the intended signal.
- Lint (`ruff check .`) and format (`ruff format --check .`) clean. CI green on
  `main`.

## Consequences

**Positive**: a real, working, recognizable-tool monitoring mechanism; human-
readable persisted metrics with linked pass/fail status and plain-language
thresholds; demonstrated recurrence across two runs; a documented interpretation
layer distinguishing "automated FAIL" from "actual problem" — directly exercising
the project's established "read actual state, don't assume it" principle.

**New Technical Debt #27**: `flatten_evidently_report`'s extraction depends on
Evidently's internal `report.dict()` schema (`metric.id`/`metric_name`,
`test.metric_config.metric_id`, `test.description`), which is not a stable public
contract and may break on a future Evidently version bump. A defensive raw-JSON
fallback exists so the notebook won't hard-fail, but it won't restore readability
without a manual fix. **A concrete instance of this risk already occurred**: the
first working extraction guessed the wrong key path for linking tests to metrics,
which silently defaulted nearly every metric to `"NO_TEST"` rather than its real
pass/fail status — the run's own console summary reported "0 non-passing" not
because everything passed, but because almost nothing was actually being checked.
The two real `FAIL` statuses were only found after the extraction was corrected
against directly-inspected real output and the table was queried by hand.

**New Technical Debt #28**: `ced.inference.detection_results`'s persisted
`FEATURE_COLUMNS` are raw (non-imputed) Gold values, not the values actually fed to
the model. This corrects an inaccurate claim made in ADR-016 / Milestone 10's
`current-context.md` section. Not fixed at the source — would require re-running
`batch_inference.py` and rewriting the table, explicitly out of scope (no further
inference runs planned) — but the monitoring notebook independently applies the
correct imputation, and this record exists so the inaccuracy doesn't propagate
silently.

**Existing Technical Debt #22** (sample, not genuinely new data) is now
load-bearing for correctly interpreting this milestone's near-zero-drift result —
stated explicitly here so "0 of 8 features drifted" isn't read as a stronger claim
than it is.

**No pipeline-level (orchestration) monitoring implemented** — deferred to
Milestone 12 per roadmap ordering, consistent with the standing decision not to
build orchestration-dependent monitoring against manually-run notebooks.

**Computed in pandas** (`Dataset.from_pandas`), not PySpark-native — a real
scale limitation (driver-memory bound at the current 500-row scale). A PySpark-at-
scale approach is documented separately as teaching content, not implemented this
milestone.

## Future Considerations

- Re-run monitoring against a genuinely new (non-overlapping) inference batch if
  one is ever produced, to get a real (non-negative-control) drift comparison.
- Evidently Test Suites wired to actual pipeline gating once Airflow orchestration
  exists (Milestone 12+) — e.g., fail a DAG task when `DriftedColumnsCount` share
  exceeds a threshold.
- Distributed/PySpark-native drift computation if data volume exceeds
  driver-memory limits.