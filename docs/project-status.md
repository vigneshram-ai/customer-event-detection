# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 11_

_Milestone 11 status: IMPLEMENTED AND VERIFIED — a monitoring notebook runs two
Evidently `Report`s (`DataDriftPreset` current-vs-reference on the 8 Gold features;
`DataSummaryPreset` standalone on the current batch including
`detection_score`/`detection_flag`) against `ced.inference.detection_results`
(treated, per explicit scope decision, as the batch under monitoring), renders both
as inline HTML, and persists flattened, human-readable results to a new
`ced.monitoring.batch_quality_report` table. Two independent runs confirmed
deterministic, reproducible output and correct append-mode accumulation. See
ADR-017 for the full design, including the auto-select-vs-PSI correction, the
Milestone 10 feature-imputation correction discovered along the way, and the
interpretation of two benign `FAIL` statuses in the quality metrics._

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified

**Milestones 1–9** — unchanged from prior status; see git history / earlier
versions of this file for full detail.

**Milestone 10 — Batch inference**
- Unchanged from prior status, **with one correction**: the persisted
  `FEATURE_COLUMNS` in `ced.inference.detection_results` are raw (non-imputed) Gold
  values, not the `fillna(0)`-imputed values actually fed to the model —
  Milestone 10's imputation fix was applied to the transient scoring matrix only
  and never propagated to the output write. `detection_score`/`detection_flag`
  themselves are unaffected and correct. See Technical Debt #28 and ADR-017.

**Milestone 11 — Monitoring**
- **Design decisions resolved and documented in ADR-017**, covering: the decision
  to use Evidently directly for every monitoring metric rather than hand-rolled
  statistics; the correction from an initially-forced PSI method to Evidently's
  auto-selected per-column tests, after review against a real sample Evidently
  output showed the original comparability justification was wrong; the decision
  to treat Milestone 10's sample-based batch as the batch under monitoring, with
  the resulting near-zero-drift result explicitly framed as a negative control
  rather than a genuine finding; the discovery and correction of the Milestone 10
  feature-imputation inaccuracy; and the empirical verification (through two
  incorrect guesses, then direct inspection) of Evidently's `report.dict()` schema.
- **`notebooks/monitoring.py`** — new Databricks notebook. Requires
  `%pip install evidently` (not in the managed runtime), following the
  established install → `dbutils.library.restartPython()` → import pattern,
  covered by the existing `"notebooks/*.py" = ["E402"]` ruff per-file-ignore
  (no `pyproject.toml` change needed).
  - Loads reference (`ced.gold.customer_events_features`) and current
    (`ced.inference.detection_results`) as pandas, applies `fillna(0)` to both
    sides' `FEATURE_COLUMNS` for parity (replicating `train_model.py`'s exact
    preprocessing).
  - Builds Evidently `Dataset`s with explicit `DataDefinition` (binary 0/1 flags
    declared categorical, not numerical).
  - Runs `Report([DataDriftPreset()], include_tests="True")` current-vs-reference
    on the 8 features, and `Report([DataSummaryPreset()], include_tests="True")`
    standalone on the current batch (8 features + `detection_score` +
    `detection_flag`).
  - Saves both reports as HTML, rendered inline via `displayHTML`.
  - Flattens results into `ced.monitoring.batch_quality_report`
    (`run_id`, `scored_at`, `metric_category`, `metric_name`, `value`,
    `threshold`, `status`), written with `mode("append")`. Extraction uses
    Evidently's confirmed real schema (`metric.id`/`metric_name`,
    `test.metric_config.metric_id`, `test.description`), with a defensive
    raw-JSON fallback if that schema changes in a future Evidently version.
- **New `ced.monitoring` schema and `batch_quality_report` table** created
  (`CREATE SCHEMA IF NOT EXISTS ced.monitoring;`).
- **Real run verified** against live Databricks (Free Edition), twice
  independently:
  - 79 metric rows per run (9 drift + 70 data-quality/summary), 158 total.
  - All metric values identical across both runs — confirms deterministic
    computation and correct append accumulation across multiple runs (a
    verification of the recurrence design beyond this milestone's original
    scope).
  - **Drift**: `DriftedColumnsCount` share = 0.0 (0 of 8 features drifted).
    Per-column `ValueDrift` scores ranged ~0.006–0.064 (threshold 0.1), all
    `TestStatus.SUCCESS`. Explicitly interpreted in ADR-017 as an expected
    negative-control result (the current batch is a subset of the reference
    population), not a genuine drift-detection finding.
  - **Data quality**: all tested metrics passed except two, both interpreted as
    benign, real, correctly-detected structural properties of the dataset rather
    than defects — `DuplicatedRowCount() = 18` (checked columns exclude
    identifiers; sparse features legitimately produce shared feature vectors
    across distinct events) and `AlmostConstantColumnsCount() = 5` (the 5 flagged
    columns are rare-event indicators by design — low prevalence is the intended
    signal).
  - CI confirmed green (lint, format, tests) on this change.
- **A real bug caught and corrected, not left as silent debt**: implementing the
  monitoring notebook's null-safety assertion surfaced that
  `ced.inference.detection_results`'s persisted feature columns are raw, not
  imputed, contradicting Milestone 10's ADR-016 claim. Corrected in this file and
  `current-context.md` rather than silently patched around.
- **Two extraction-schema mistakes caught and corrected via direct inspection,
  not repeated guessing**: the working `flatten_evidently_report` function is
  based on real `report.dict()` output the user pasted, not documentation or
  assumption — consistent with the project's "read actual state" pattern.
- **A design correction made under direct challenge**: the original
  forced-PSI decision was reversed after the user provided a real counter-example
  Evidently output showing auto-selected tests already solve cross-feature
  comparability — documented in ADR-017 as a corrected, not silently
  abandoned, decision.

### 🟡 Implemented, Not Fully Verified
- **`validate_and_promote_model.py`'s champion-vs-challenger comparison
  branch** (Milestone 9) — not yet exercised against live output.
- **`batch_inference.py`'s exact resolved `model_version` string** —
  inferred, not directly observed (Technical Debt #26).

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
- Time-of-day deviation feature.
- `ced.training` schema access restricted to a training-job identity — cannot be
  enforced on Free Edition (single-user).
- Live/shadow evaluation for the champion/challenger pattern.
- A genuinely new/unseen event batch for inference (would also let Milestone 11's
  monitoring produce a real, non-negative-control drift result).
- Distributed (`spark_udf`-based) batch scoring and a custom `PythonModel`-based
  flavor-agnostic probability output.
- Pipeline-level (orchestration) monitoring — requires Airflow orchestration
  (Milestone 12) to be meaningful; not attempted against manually-run notebooks.
- Evidently Test Suites wired to actual pipeline gating (e.g., failing a future
  DAG task on `DriftedColumnsCount` share exceeding a threshold) — discussed in
  ADR-017 as a Milestone 12+ extension, not implemented.
- PySpark-native (distributed) drift/quality computation for larger-than-driver-
  memory datasets — discussed as a scaling consideration, not implemented (see
  conversation for the teaching walkthrough).

### ⏳ Future
- Verifying the champion/challenger comparison branch with a real second model
  version.
- A genuinely new event batch for batch inference.
- Append/dedup strategy for `ced.inference.detection_results`.
- Re-running monitoring against a genuinely new (non-overlapping) batch, once one
  exists, to get a real drift comparison rather than a negative control.
- Milestone 12 onward per the approved roadmap: real Airflow orchestration,
  security, full CI/CD.

---

## Current Work
None in progress. Milestone 11 is closed.

## Pending Work
Milestones 12–23 per the approved roadmap. Next up is Milestone 12 (Airflow real
orchestration, replacing the temporary smoke-test DAG), not yet scoped in detail —
do not begin without explicit user confirmation.

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor` (not Celery) for local development | **ADR-009** |
| Local→Databricks ingestion via `databricks-sdk` standalone script + Databricks notebook | **ADR-010** |
| Bronze writes use `mode("overwrite")`, not append | **ADR-010** |
| Silver validation is PySpark-native; quarantine failure handling | **ADR-011** |
| Gold window features end at `-1` relative to current row; no quarantine path | **ADR-012** |
| Baseline detector uses fixed, additive point-scoring rules | **ADR-013** |
| Ground truth isolated to `ced.training`, in-memory-only join to features | **ADR-014** |
| Model validation gate: three thresholds, no recomputation; alias-based promotion | **ADR-015** |
| Batch inference scores a reproducible sample of existing Gold data; generic `pyfunc.load_model` + sklearn unwrap for `predict_proba`; `fillna(0)` train/serve parity (scoring matrix only — see ADR-017 correction) | **ADR-016** |
| Monitoring uses Evidently directly (no hand-rolled statistics); auto-selected drift tests (not forced PSI); Milestone 10's batch treated as current-under-monitoring with explicit negative-control framing; reference/current imputation parity applied independently of the (corrected) upstream gap; extraction verified against Evidently's real `report.dict()` schema | **ADR-017** |
| `uv` over Poetry/pip; `ruff` for lint + format | Recorded here only |

Full ADR-002 ("Airflow as the Orchestration Layer") remains pending.

---

## Known Issues
- None blocking. CI confirmed green through Milestone 11.
- `ced.inference.detection_results`'s persisted feature columns are raw, not
  imputed — see Technical Debt #28. Does not affect `detection_score`/
  `detection_flag`, which are correct.

## Technical Debt
1–19. Unchanged from Milestone 8 — see prior version of this file / git history.

20. Champion/challenger comparison branch unverified against live output.
21. `archived` alias only tags the single most-recently-losing version.
22. **Milestone 10's batch inference scores a reproducible sample of existing Gold
    data, not genuinely new/unseen events.** Now also the reason Milestone 11's
    near-zero-drift result must be read as a negative control rather than a
    genuine finding — see ADR-017.
23. `predict_proba` obtained via sklearn-specific unwrap, not flavor-agnostic.
24. `ced.inference.detection_results` uses `mode("overwrite")`, no historical
    accumulation.
25. `fillna(0)` on amount-based Gold features collapses two distinct NULL causes.
26. Milestone 10's exact `model_version` output string was inferred, not directly
    observed.
27. **NEW — Monitoring's Evidently-output extraction (`flatten_evidently_report`)
    depends on Evidently's internal `report.dict()` schema** (`metric.id`/
    `metric_name`, `test.metric_config.metric_id`, `test.description`), which is
    not a documented, stable public contract. Verified empirically against real
    output for the current Evidently version; may break silently readable-name-
    wise on a future version bump. A defensive raw-JSON fallback prevents a hard
    failure but won't restore human-readable metric names automatically — would
    need re-verification against the new version's real output, same process used
    to build the current extraction.
28. **NEW — `ced.inference.detection_results`'s persisted `FEATURE_COLUMNS` are
    raw (non-imputed) Gold values, not the values actually fed to the model.**
    Milestone 10's `fillna(0)` fix (ADR-016) was applied to the transient scoring
    matrix passed to `predict_proba` only; it was never propagated to the `pdf`
    written to the output table. `detection_score`/`detection_flag` themselves
    are correct (computed from the properly-imputed matrix) — only the persisted
    feature columns are affected. This corrects an inaccurate claim made in
    ADR-016 and Milestone 10's `current-context.md` section. Not fixed at the
    source (would require re-running `batch_inference.py`; no further inference
    runs are planned), but `notebooks/monitoring.py` independently applies the
    correct imputation before any comparison, so Milestone 11's results are not
    affected by this gap.

---

## Environment / Setup Information

| Item | Value | Verification status |
|---|---|---|
| OS | Windows (native, no WSL2 terminal use) | Stated by user |
| Project Python (via `uv`) | 3.11.16 | ✅ Verified |
| `uv` version | 0.12.5 | Stated by user |
| Docker Desktop | Running, Linux containers via WSL2 backend | 🟡 Inferred |
| Git | `main` branch, GitHub remote connected, 2.55.0.windows.4 | ✅ Verified |
| Databricks workspace | Free Edition, `https://dbc-01205ae9-f87b.cloud.databricks.com/`, serverless compute only | ✅ Verified |
| Unity Catalog catalog | `ced` | ✅ Verified |
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold`, `ced.training`, `ced.models`, `ced.inference`, `ced.monitoring` | ✅ Verified (`monitoring` new in Milestone 11) |
| Unity Catalog model registry | `ced.models.logistic_regression_detector` v1 (alias `champion`), `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified |
| `ced.inference.detection_results` | 500 rows, 12 flagged (2.40%); feature columns raw, not imputed (Technical Debt #28) | ✅ Verified (with caveat) |
| `ced.monitoring.batch_quality_report` | 158 rows (2 runs × 79 metrics); 9 drift + 70 quality/summary per run; identical across runs | ✅ Verified |

## Repository Structure (as of Milestone 11)
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
│ │ ├── ADR-009 … ADR-016 (unchanged)
│ │ └── ADR-017-monitoring-strategy.md
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
├── monitoring/ (empty — Databricks-only logic, same pattern as other notebooks)
├── data/ (gitignored)
├── airflow/
├── tests/
├── docker/ (empty)
└── .github/workflows/ci.yml
```

Note: local `monitoring/` package directory remains empty — Milestone 11's logic
lives entirely in `notebooks/monitoring.py`, consistent with the project's
Databricks/Spark-only-logic pattern.

## Installed Dependencies

**Production**: `databricks-sdk>=0.133.0`, `python-dotenv>=1.2.3`, `pandas`.
Databricks-side only (not `pyproject.toml` dependencies): `xgboost`, `mlflow`,
`evidently` (new, Milestone 11).

**Dev**: `pytest>=8.3.0`, `ruff>=0.6.0`.

No new local dependencies introduced in Milestone 11 — `monitoring.py` uses
`evidently`, `pandas`, and PySpark, all Databricks-managed or already installed
via `%pip install`.

## Databricks Status
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`, `models`,
  `inference`, `monitoring` (new in Milestone 11)
- `ced.monitoring.batch_quality_report` — new in Milestone 11, 158 rows,
  `mode("append")`
- All other Databricks-side state unchanged from Milestone 10
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — not yet orchestrating any part of this
  project's real pipeline. Deferred to Milestone 12.

## Testing Setup
- Unchanged: 34 tests, no automated coverage for Databricks/Spark-only notebooks
  (consistent pattern — `monitoring.py` follows the same approach).

## Linting/Formatting Setup
- No new lint/format exceptions required. `monitoring.py`'s `%pip install` /
  restart pattern is covered by the existing `"notebooks/*.py" = ["E402"]`
  per-file-ignore. Real lint issues surfaced during development (`dbutils`/
  `displayHTML` undefined-name errors from Databricks runtime globals not being
  explicitly imported) were fixed with explicit `from databricks.sdk.runtime
  import ...` statements — consistent with this project's established recurring
  bug pattern for `dbutils`/`spark` runtime globals, now extended to
  `displayHTML`.

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to
  `main`.
- ✅ Confirmed green on `main` through Milestone 11 (per user confirmation).
- Still does not build/run Docker, Airflow, or touch Databricks (by design).

## Commands Used to Verify Milestone 11
```sql
CREATE SCHEMA IF NOT EXISTS ced.monitoring;
```
`notebooks/monitoring.py` run manually via "Run All" in the Databricks workspace,
twice independently (distinct `run_id`s each time). No local commands required
for the Databricks-side verification; `uv run ruff check .` and
`uv run ruff format --check .` run locally to verify lint/format.

Observed output (`notebooks/monitoring.py`, condensed):
```text
Wrote 79 metric rows to ced.monitoring.batch_quality_report (run_id=...)
Drift metrics: 9  |  Summary/quality metrics: 70
Rows with a non-passing/unexpected status: 0   # (run 1's filter; see note below)
```
Full persisted table query (`SELECT metric_category, metric_name, value, status
FROM ced.monitoring.batch_quality_report ...`) confirmed, across both runs:
- Drift: `DriftedColumnsCount(drift_share=0.5)` = `{'count': 0.0, 'share': 0.0}`,
  `TestStatus.SUCCESS`; all 8 per-feature `ValueDrift(...)` scores between
  0.0062 and 0.0644 (threshold 0.1), all `TestStatus.SUCCESS`.
- Data quality: all `TestStatus.SUCCESS` except `DuplicatedRowCount() = 18.0`
  (`TestStatus.FAIL`, interpreted as benign) and
  `AlmostConstantColumnsCount() = 5.0` (`TestStatus.FAIL`, interpreted as
  benign) — see ADR-017 for the interpretation. **Note**: the very first
  run's own console summary ("Rows with a non-passing/unexpected status: 0")
  was misleading, not confirmatory — the extraction code at that time linked
  tests to metrics via the wrong key path (`t.get("metric_id")` instead of
  `t["metric_config"]["metric_id"]`), so nearly every metric silently
  defaulted to `"NO_TEST"` rather than its real status. The message reported
  that almost nothing was being checked, not that everything passed. The two
  real `FAIL`s were only surfaced once the extraction was corrected and the
  table was queried directly. The notebook's console filter has since been
  corrected to match Evidently's actual status format
  (`"TestStatus.SUCCESS"`), so future runs' summary prints will be
  meaningful.