# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 9_

_Milestone 9 status: IMPLEMENTED AND VERIFIED (for LogisticRegression) —
a validation gate reads already-logged Milestone 8 MLflow metrics for
`ced.models.logistic_regression_detector`'s latest version (no
recomputation) and checks three thresholds: `recall_channel_deviation`,
overall `recall` (both >= 0.95), and `precision` (>= 0.90, deliberately
below the M7 baseline's 1.0000 per Technical Debt #19's non-like-for-like
basis). On pass, the version is promoted via a Unity Catalog model alias
(`champion`) — UC's current alias-based mechanism, replacing the deprecated
stage-based promotion. A full champion/challenger/previous_champion/
archived alias policy is implemented for future retrains, but only the
"no existing champion" branch has been exercised against live output so
far — see ADR-015 for the specific IMPLEMENTED-NOT-YET-VERIFIED caveat on
the comparison branch. XGBoost is deliberately excluded from the gate this
milestone (see ADR-015)._

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
- **Design decisions resolved and documented in ADR-015**, covering: gate
  threshold selection and rationale (why precision's floor is below the
  baseline's), alias-based promotion (UC deprecated stage-based
  promotion), the champion/challenger/previous_champion/archived alias
  semantics (all project-defined conventions, not UC built-ins), the
  decision to compare challenger vs. champion on F1 with ties favoring
  the incumbent, and the deliberate exclusion of XGBoost from this
  milestone's gate.
- **`notebooks/validate_and_promote_model.py`** — new Databricks notebook.
  Resolves the *latest* registered version of
  `ced.models.logistic_regression_detector` dynamically (not a hardcoded
  run name or version number, so it remains correct across future
  retrains), reads that version's already-logged MLflow metrics, applies
  the three-check gate, and on pass:
  - No existing `champion` → promotes the version directly.
  - A different `champion` exists → tags the version `challenger`
    immediately (this is what defines it as a challenger), then compares
    it to the champion on F1: strictly greater F1 promotes it to
    `champion` (outgoing champion tagged `previous_champion`, `challenger`
    alias retired); equal-or-lower F1 removes the `challenger` alias and
    tags the version `archived` instead (this project runs one-shot batch
    comparison, not live shadow evaluation, so a losing version has no
    honest "still being evaluated" state to hold).
  - Gate failure aborts entirely — no alias touched, non-zero exit.
- **Real run verified** against live Databricks (Free Edition), first-ever
  run against `logistic_regression_detector` (no prior `champion`
  existed):
  [PASS] recall_channel_deviation: 1.0000 (threshold >= 0.95)
  [PASS] recall: 1.0000 (threshold >= 0.95)
  [PASS] precision: 0.9879 (threshold >= 0.90)

  GATE PASSED — no existing champion. v1 promoted directly to 'champion'.

  Final registered aliases:
  champion -> v1

    Confirms Free Edition supports `set_registered_model_alias` /
  `get_registered_model(...).aliases` — previously unverified, same
  pattern as M8's confirmation that model registration itself worked.
- **XGBoost remains registered but outside this milestone's gate** —
  deliberate scope decision (see ADR-015), not an oversight; it
  underperforms LogisticRegression on every M8 metric.
- **Design iteration caught three real gaps before implementation was
  finalized** (all resolved in the version above, not left as debt):
  1. An earlier draft assumed a 1:1 run-to-version mapping (looking up
     model version by `run_id` filtered on a fixed run *name*) — would
     have broken on the first retrain, since retraining produces new runs
     with new `run_id`s and the same name. Fixed by resolving the latest
     *registered version* directly via `search_model_versions`, then
     working backward to its run — no assumption about run naming at all.
  2. An earlier draft implemented `champion`-only promotion with no
     `challenger` concept — discarded the standard champion/challenger
     MLOps pattern for no architectural reason. Fixed by adding the
     comparison-on-F1 logic above.
  3. An earlier draft assigned the `challenger` alias only *after* losing
     a comparison — meaning the alias's real, forward-looking meaning
     ("currently being evaluated against champion") was never actually
     represented, and a losing version silently overwrote any prior
     `challenger` regardless of relative merit. Fixed by assigning
     `challenger` immediately on gate-pass (before comparison), and
     retagging losers `archived` instead of leaving them mislabeled
     `challenger` indefinitely.

### 🟡 Implemented, Not Fully Verified
- **`validate_and_promote_model.py`'s champion-vs-challenger comparison
  branch** (F1 tie-break, `previous_champion` tagging, `challenger`/
  `archived` handling) — implemented and reasoned in ADR-015, but not yet
  exercised against live output. The only run so far took the
  "no existing champion" path (since none existed). Verifying the
  comparison branch requires a second model version (e.g. a deliberate
  retrain) — flagged as a follow-up verification step, not new milestone
  scope.

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
- Time-of-day deviation feature — implementation drafted and then removed;
  approach documented in ADR-012, not verified end-to-end.
- `ced.training` schema access restricted to a training-job identity,
  distinct from an inference-job identity — the intended RBAC boundary
  per ADR-014, but Free Edition is single-user, so this cannot actually be
  enforced or demonstrated.
- Live/shadow evaluation for the champion/challenger pattern (running a
  challenger against real inference traffic before deciding) — the
  current implementation is one-shot batch comparison only; genuine shadow
  evaluation would require batch inference to exist first (Milestone 10+).

### ⏳ Future
- Time-of-day deviation, if revisited — needs its own design-implement-verify
  cycle per ADR-012.
- Verifying the champion/challenger comparison branch with a real second
  model version.
- Milestone 10 onward per the approved roadmap: batch inference against
  new events (querying `@champion` directly), monitoring, security, full
  CI/CD, Airflow real orchestration at Milestone 12.

---

## Current Work
None in progress. Milestone 9 is closed for LogisticRegression.

## Pending Work
Milestones 10–23 per the approved roadmap, next up being batch inference
against new customer events using the `@champion` alias. Not yet scoped in
detail — do not begin without explicit user confirmation.

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
| Model validation gate reads already-logged metrics (no recomputation); three thresholds — `recall_channel_deviation`/`recall` >= 0.95, `precision` >= 0.90 (deliberately below baseline's 1.0000, non-like-for-like basis) | **ADR-015** |
| Promotion via Unity Catalog model aliases (`champion`/`challenger`/`previous_champion`/`archived`), not deprecated stage-based promotion; alias semantics are project-defined conventions, not UC built-ins | **ADR-015** |
| Champion vs. challenger comparison uses F1 (single decisive metric, already logged), ties favor the incumbent champion | **ADR-015** |
| `challenger` alias assigned on gate-pass, before comparison (not as a post-hoc loser label); losers retagged `archived` instead of indefinitely mislabeled `challenger`, since this project implements one-shot batch comparison, not live shadow evaluation | **ADR-015** |
| XGBoost deliberately excluded from Milestone 9's gate — underperforms LogisticRegression on every M8 metric | **ADR-015** |
| `uv` over Poetry/pip | Recorded here only — tooling preference |
| `ruff` for lint + format (single tool) | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV | Recorded here only (Milestone 3) |

Full ADR-002 ("Airflow as the Orchestration Layer" broadly) remains pending.

---

## Known Issues
- None blocking. CI confirmed green on `main` through Milestone 8 (Milestone 9's notebook has no automated test coverage — Databricks/Spark-only, consistent with the project's stated no-local-PySpark-harness pattern).

## Technical Debt
1–19. Unchanged from Milestone 8 — see prior version of this file / git
history for full text.
20. **The champion/challenger comparison branch in
    `validate_and_promote_model.py` is implemented but not yet exercised
    against live output** — only the "no existing champion" path has run.
    Requires a second model version to verify (e.g. a deliberate retrain).
    Not a defect; a stated verification gap per ADR-015.
21. **The `archived` alias only tags the single most-recently-losing
    version** — earlier losing versions remain in the registry (immutable,
    queryable by version number) but lose the alias tag once a newer
    version is archived. Full loss history is not queryable via alias
    alone. Deliberately left as-is; a naming convention for per-version
    archival tags would resolve this if ever needed.

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
| Unity Catalog model registry | `ced.models.logistic_regression_detector` v1 (alias `champion`), `ced.models.xgboost_detector` v1 (no alias) | ✅ Verified |

## Repository Structure (as of Milestone 9)
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
│ │ └── ADR-015-model-validation-and-promotion.md
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
│ └── validate_and_promote_model.py
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

No new dependencies introduced in Milestone 9 — `validate_and_promote_model.py`
uses only `mlflow.tracking.MlflowClient`, already available in the
Databricks-managed MLflow runtime.

## Databricks Status
- Edition: Free Edition, serverless compute only
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`, `training`, `models`
- Bronze/Silver/Gold/training tables: unchanged from Milestone 8
- `ced.models.logistic_regression_detector` v1 — alias `champion` (new in
  Milestone 9)
- `ced.models.xgboost_detector` v1 — no alias (deliberately outside M9's
  gate)
- MLflow experiment `/Shared/customer_event_detection_m8`: unchanged, 3
  runs (Milestone 9 reads from it, does not add runs)
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — not yet orchestrating any part of this
  project's real pipeline.

## Testing Setup
- Framework: `pytest`
- Current coverage: environment (2), customer generator (7), event
  generator (19), upload-to-volume (3), upload-ground-truth (3) —
  **34 total**, unchanged in Milestone 9
- No automated coverage for any Databricks/Spark-only notebook, consistent
  with the project's stated no-local-PySpark-harness reasoning —
  `validate_and_promote_model.py` follows this same pattern.

## Linting/Formatting Setup
- Unchanged from Milestone 8. No new lint/format exceptions required in
  Milestone 9 — `validate_and_promote_model.py` needed no `%pip install`,
  so the `E402` per-file-ignore situation does not recur here.

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- ✅ Confirmed green on `main` through Milestone 8; Milestone 9 introduces
  no new testable Python module (Databricks notebook only), so no CI
  changes expected — to be confirmed once committed.
- Still does not build/run Docker, Airflow, or touch Databricks (by design)

## Commands Used to Verify Milestone 9
(Databricks notebook — `validate_and_promote_model.py` — run manually via
"Run All" in the Databricks workspace; no local commands required for this
milestone.)

Observed output (`notebooks/validate_and_promote_model.py`):