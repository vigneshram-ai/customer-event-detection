# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 7_

_Milestone 7 status: IMPLEMENTED AND VERIFIED — rule-based baseline detector
built, run end-to-end against live Databricks, and evaluated against
Milestone 3 ground-truth anomaly labels for the first time in this project.
One Spark null-semantics bug and one recurring `spark`-runtime-global bug
were caught and fixed during verification. A structural (by-design, not a
bug) recall gap on `channel_deviation` anomalies was identified, documented,
and deliberately left untuned — see ADR-013._

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified

**Milestone 1 — Repository & local dev environment**
- Repository skeleton, Git, `pyproject.toml` (`uv`, PEP 735 dependency groups), `ruff`,
  `pytest`, Airflow 3.3.1 (`LocalExecutor`, Docker Compose, 5 healthy containers),
  GitHub Actions CI green.

**Milestone 2 — Synthetic customer generator**
- `data_generation/customer_generator.py` (stdlib only), seeded/deterministic,
  weighted country/channel/account-age-tier distributions. 7 tests passing.
- Output: `data/raw/customers.csv`.

**Milestone 3 — Synthetic event generator**
- `data_generation/event_generator.py` (stdlib only), 9 weighted event types, 4
  anomaly types, ground truth in a separate sidecar file. 19 tests passing.
- Real end-to-end run verified: 1,000 customers → 27,128 events, 542 anomalies
  (2.00%, matching configured `--anomaly-rate`).
- Output: `data/raw/events.csv`, `data/raw/events_ground_truth.csv`.

**Milestone 4 — Bronze-layer ingestion (Databricks/Delta)**
- Local→Databricks handoff mechanism designed, implemented, documented in **ADR-010**.
- `ingestion/upload_to_volume.py` — `databricks-sdk` `WorkspaceClient` upload of
  `customers.csv`/`events.csv` to `ced.bronze.raw_uploads`. Excludes the
  ground-truth sidecar deliberately. 3 tests, SDK client mocked.
- `notebooks/bronze_ingestion.py` — explicit `StructType` schemas, header-validation
  gate, row-count integrity check, audit columns (`_ingested_at`, `_source_file`),
  `mode("overwrite")` writes.
- Real end-to-end run verified against live Databricks: `ced.bronze.customers` —
  1,000 rows, `ced.bronze.events` — 27,128 rows.
- Known limitation investigated and accepted: Databricks' Photon CSV reader
  converts intentional empty-string `merchant_category` values to `NULL`. Deferred
  to Silver (resolved in Milestone 5).
- First production dependencies added: `databricks-sdk`, `python-dotenv`. Secrets
  in git-ignored `.env`.
- Full test suite: 31 passed, `ruff check`/`ruff format --check` clean, CI
  confirmed green on `main` (after a `spark`/`display` lint fix — Databricks
  runtime globals resolved via `from databricks.sdk.runtime import display, spark`).

**Milestone 5 — Silver-layer cleaning and validation**
- **Design decisions resolved and documented in ADR-011**: validation mechanism
  (PySpark-native, not Great Expectations/Pandera/DLT expectations) and failure
  handling (quarantine to a `_rejects` table, not hard-fail or silent drop).
- `notebooks/silver_transformation.py` — customer and event validation, referential
  integrity against cleaned customers, quarantine to `_rejects` tables with
  `_rejection_reasons` arrays, row-count reconciliation on every write.
- `merchant_category` NULL caveat from ADR-010 formally resolved (NULL valid for
  6 non-monetary event types, flagged only on monetary types).
- `amount = 0.0` accepted as the non-monetary sentinel value (not regenerated at
  source) — deliberate trade-off, documented in ADR-011.
- `.cache()` removed after `NOT_SUPPORTED_WITH_SERVERLESS` on Databricks Free
  Edition serverless compute.
- **Real end-to-end run verified**: `ced.silver.customers` — 1,000 valid, 0
  rejected; `ced.silver.events` — 27,128 valid, 0 rejected.
- `uv run ruff check .` / `uv run ruff format --check .` — both clean.
- No automated test coverage, consistent with Bronze — Databricks/Spark-only code.

**Milestone 6 — Gold-layer feature engineering**
- **Design decisions resolved and documented in ADR-012**: leakage-boundary
  convention, amount-feature applicability rule, the `normal_device`-counts-
  as-known definition for `is_new_device`, empty-window-frame count semantics,
  and the decision to implement-then-drop time-of-day deviation.
- `notebooks/gold_feature_engineering.py` — new Databricks notebook, same
  plain-text "source" format and `CATALOG`/audit-column conventions as Bronze
  and Silver.
  - Joins `ced.silver.events` to `ced.silver.customers` (inner join; verified
    row-count-preserving, as guaranteed by Silver's referential-integrity check).
  - **Eight features shipped**, computed via PySpark window functions:
    - `prior_event_count_7d` — rolling 7-day event count (time-bounded range window)
    - `prior_avg_amount_90d` — rolling 90-day avg amount, monetary event types only
    - `amount_deviation_from_prior_avg` — amount minus rolling avg, monetary only
    - `is_new_device` — device is neither `normal_device` nor previously observed
    - `is_unusual_channel` — channel differs from customer's `normal_channel`
    - `is_unusual_country` — event country differs from customer's `home_country`
      (a country-mismatch proxy, not a true geo-distance metric)
    - `prior_failed_login_count_24h` — rolling 24h count of `failed_login`
      events, applies regardless of the current row's own event type
    - `time_since_last_event_seconds` — via `lag()`, NULL on a customer's first event
  - **Leakage rule enforced throughout**: every window (`rowsBetween`/
    `rangeBetween`) ends at `-1` relative to the current row — no feature ever
    sees its own event.
  - Row-count reconciliation: Gold output must exactly match Silver input count
    (no quarantine step at this layer — a mismatch here indicates a bug, e.g. a
    join fan-out, not a data-quality failure).
- **Two design-vs-implementation discrepancies caught during live verification**,
  both fixed before closing the milestone — full detail in ADR-012:
  1. `prior_avg_amount_90d` initially gated only the rolling window's *input*
     on `event_type`, not the *emitted value* — non-monetary events (e.g.
     `login`) received a real number reflecting monetary history instead of
     `NULL`. Caught by inspecting sanity-check output (non-monetary null
     counts didn't equal row counts). **Fixed** by gating the emitted value on
     the current row's own `event_type` as well.
  2. `prior_failed_login_count_24h` initially returned `NULL` (not `0`) for
     ~70% of rows (19,062 of 27,128) whenever a customer had no failed-login
     history in the preceding 24 hours. Root cause: **Spark's `SUM` over an
     empty window frame returns `NULL`, not the identity value `0`** —
     general Spark behavior, not specific to this dataset. Caught the same
     way — the sanity check expected `0` nulls and got 19,062. **Fixed** with
     `F.coalesce(..., F.lit(0))`.
- **Time-of-day deviation was implemented (circular-statistics hour-angle
  approach), then deliberately removed** before final verification — the
  complexity wasn't justified without a concrete downstream need yet. Cut
  after seeing the actual implementation, not before. Documented as a
  reusable draft approach in ADR-012 if revisited later.
- **Real end-to-end run verified** against live Databricks, after both fixes:
  - `ced.gold.customer_events_features` — 27,128 rows, exact 1:1 reconciliation
    with `ced.silver.events` (0% row loss).
  - `is_new_device`: 229 true (~0.8%); `is_unusual_channel`: 128 true (~0.5%);
    `is_unusual_country`: 128 true (~0.5%).
  - `time_since_last_event_seconds` NULL exactly 1,000 times — one per
    customer's first event, confirming correct per-customer window scoping.
  - `prior_failed_login_count_24h` NULL count: **0** (confirmed after the
    coalesce fix — was 19,062 before).
  - `prior_avg_amount_90d` / `amount_deviation_from_prior_avg`: confirmed 100%
    NULL for every non-monetary event type (`beneficiary_added`,
    `device_changed`, `failed_login`, `login`, `password_changed`,
    `profile_changed`) — row count exactly equals null count in each case.
    Monetary types (`card_transaction`, `payment`, `transfer`) show partial
    nulls only, corresponding to events before each customer's first monetary
    transaction.
- `uv run ruff check .` / `uv run ruff format --check .` — both clean.
- CI confirmed green on this milestone's commit.
- No automated test coverage, consistent with Bronze/Silver — Databricks/Spark-
  only code, no local PySpark harness in this project.

**Milestone 7 — Baseline rule-based detector**
- **Design decisions resolved and documented in ADR-013**: additive point-
  scoring vs. OR-logic, fixed-vs-swept thresholds (fixed, to avoid leakage
  against ground truth), and detector-on-Databricks/evaluation-local split.
- `notebooks/baseline_detector.py` — new Databricks notebook, reads
  `ced.gold.customer_events_features`, applies a 7-rule additive point score
  across 5 of the 8 Gold features (2 features — `prior_event_count_7d`,
  `time_since_last_event_seconds` — deliberately excluded from scoring,
  carried as context only).
  - Output: `ced.gold.baseline_detections` — `customer_id`, `event_id`,
    `event_timestamp`, `detection_score`, `detection_flag`, `reason`
    (array<string>), `model_version` (`"baseline_rule_v1"`), `scored_at`,
    plus two context-only columns.
  - Row-count reconciliation: 27,128 output rows exactly match 27,128 Gold
    input rows, no filtering (same no-quarantine convention as Gold).
  - Exports a flattened CSV (`reason` array joined with `;`) to a new Unity
    Catalog volume, `ced.gold.exports`, for local evaluation.
- `evaluation/evaluate_baseline.py` — new local script. Downloads the export
  via `databricks-sdk`, joins against `data/raw/events_ground_truth.csv` on
  `event_id`, computes precision/recall/F1/false-positive-rate, and a recall
  breakdown by `anomaly_type`. **First use of `pandas` in this project** —
  added as a production dependency.
- **Two bugs caught during live verification, both fixed before closing the
  milestone** — full detail in ADR-013:
  1. `F.array_remove(array, None)` silently nulled the entire `reason`
     column on every row (Spark null-value-removal semantics, not a
     null-filter). Caught because the exploded rule-frequency sanity check
     came back empty. Fixed with `F.filter(array, lambda x: x.isNotNull())`.
  2. `NameError: spark is not defined` — same root cause as the Milestone 4
     Bronze notebook fix, now a confirmed recurring pattern in this project.
     Fixed identically: `from databricks.sdk.runtime import spark`.
- **Real end-to-end run verified** against live Databricks, then evaluated
  against ground truth:
  - `ced.gold.baseline_detections` — 27,128 rows, exact reconciliation.
  - Score distribution: 26,589 rows at score 0; 136 at score 1; 403 at score
    2 (no row exceeded score 2 in this dataset — no simultaneous multi-signal
    events, consistent with the M3 generator's single-event-level anomaly
    injection, technical debt #4).
  - `detection_flag = True`: 403 rows (1.49%).
  - **Precision: 1.0000, Recall: 0.7435, F1: 0.8529, FPR: 0.0000** — 403/403
    flagged events were genuine injected anomalies (0 false positives across
    27,128 events); 403/542 total injected anomalies caught.
  - Recall by anomaly type: `new_device` 100% (229/229), `geo_deviation` 100%
    (128/128), `amount_spike` 80.7% (46/57), `channel_deviation` **0%**
    (0/128, structural limitation — see below).
- **Known, deliberate limitation (not a bug, not retuned)**: `channel_deviation`
  anomalies are structurally unreachable by this baseline. `is_unusual_channel`
  correctly fires on all 128 such anomalies but is worth only 1 point against
  a flag threshold of 2, and never co-occurs with another signal in this
  dataset. Retained as an honest limitation and named motivator for
  Milestone 8, per the explicit decision not to tune thresholds against
  ground truth. Full rationale in ADR-013.
- `uv run ruff check .` / `uv run ruff format --check .` — both clean after
  the `spark` import fix.
- CI confirmed green on this milestone's commit.
- No automated test coverage for `baseline_detector.py`, consistent with
  Bronze/Silver/Gold (Databricks/Spark-only code). `evaluate_baseline.py` is
  local pure-Python — worth considering for test coverage in a future
  milestone (not done yet).

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
  Only the narrower executor/version decision (ADR-009) and the ingestion/
  validation/feature-engineering/baseline-detector decisions (ADR-010,
  ADR-011, ADR-012, ADR-013) exist.
- Time-of-day deviation feature — implementation drafted and then removed;
  approach documented in ADR-012 as a starting point, not verified end-to-end.

### ⏳ Future
- Time-of-day deviation, if revisited — needs its own design-implement-verify
  cycle per ADR-012.
- Everything from Milestone 8 onward per the approved roadmap (ML model,
  MLflow tracking/registry, batch inference, monitoring, security, full
  CI/CD, Airflow real orchestration at Milestone 12).

---

## Current Work
None in progress. Milestone 7 is closed.

## Pending Work
Milestones 8–23 per the approved roadmap, next up being the ML model stage.
Not yet scoped in detail — do not begin without explicit user confirmation.

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
| `uv` over Poetry/pip | Recorded here only — tooling preference |
| `ruff` for lint + format (single tool) | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV | Recorded here only (Milestone 3) |
| Fixed literal default date window for event generation | Recorded here only (Milestone 3) |
| Anomaly type selection weighted by event_type | Recorded here only (Milestone 3) |

Full ADR-002 ("Airflow as the Orchestration Layer" broadly) remains pending.

---

## Known Issues
- None blocking. CI confirmed green on `main` through Milestone 7.

## Technical Debt
1. No pre-commit hook. Flagged since Milestone 1, still low priority.
2. CI does not validate the Airflow Docker Compose stack (deliberate, revisit once
   a real DAG exists at Milestone 12).
3. The Airflow smoke-test DAG (`00_environment_smoke_test.py`) is temporary
   scaffolding; removal scheduled for Milestone 12.
4. Anomaly injection is single-event-level only (Milestone 3 scope decision).
5. Only `new_device` anomaly type has event-type-aware logic (Milestone 3 scope
   decision).
6. Bronze ingestion is not yet orchestrated by Airflow — deliberate, deferred to
   Milestone 12 per ADR-010.
7. Bronze writes use `overwrite`, not `append` — no ingestion history retained
   across repeated runs. Acceptable at current scope.
8. `amount = 0.0` is indistinguishable from a genuinely zero-value monetary
   transaction for non-monetary event types, from Silver onward. Root cause is
   the M3 generator's default value choice, not a Silver bug. Full rationale in
   ADR-011. **Note (Milestone 6): this ambiguity does not propagate into Gold's
   amount features**, since those are now NULL (not 0.0) for all non-monetary
   events regardless of the Silver-layer sentinel — see ADR-012.
9. Silver ingestion is not yet orchestrated by Airflow — same deferral as Bronze,
   per Milestone 12.
10. `silver_transformation.py` has no automated test coverage (Databricks/
    Spark-only code, no local PySpark harness in this project).
11. `gold_feature_engineering.py` has no automated test coverage, same
    reasoning as Bronze/Silver.
12. Time-of-day deviation is undesigned-for-shipping — a circular-statistics
    approach was drafted and removed; if revisited, treat it as a fresh
    design-implement-verify cycle, not a resurrection of the removed code.
    See ADR-012.
13. Gold-layer feature values (`is_new_device`, `is_unusual_channel`,
    `is_unusual_country`, etc.) had not been cross-referenced against
    `events_ground_truth.csv` (the M3 anomaly labels) as of Milestone 6.
    **Resolved in Milestone 7** via the baseline detector's evaluation
    against ground truth — see items 15–16 below for what that evaluation
    surfaced.
14. `is_unusual_country` is a country-level mismatch proxy, not a true
    geo-distance calculation — the data model has no lat/long. Any future
    interpretation of this feature should account for that limitation.
15. `channel_deviation`-only anomalies are structurally unreachable by the
    Milestone 7 baseline detector (0% recall) — the responsible feature
    fires correctly but is under-weighted relative to the flag threshold,
    by deliberate design (not tuning against ground truth). Named as a
    motivator for Milestone 8's ML model, not treated as a defect to fix
    in the baseline. See ADR-013.
16. `prior_failed_login_count_24h`-based rules in the baseline detector have
    zero support in current ground truth (no injected login-burst anomaly
    type exists per technical debt #5) — architecturally sound but
    unverified against any known-anomalous case.
17. `evaluation/evaluate_baseline.py` has no automated test coverage (local
    pure-Python, unlike Bronze/Silver/Gold's Databricks-only justification —
    worth reconsidering in a future milestone).

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
| Unity Catalog schemas | `ced.bronze`, `ced.silver`, `ced.gold` | ✅ Verified |
| Unity Catalog volumes | `ced.bronze.raw_uploads`, `ced.gold.exports` | ✅ Verified |

## Repository Structure (as of Milestone 7)
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
│ │ └── ADR-013-baseline-detector-design.md
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
├── notebooks/
│ ├── bronze_ingestion.py
│ ├── silver_transformation.py
│ ├── gold_feature_engineering.py
│ └── baseline_detector.py
├── evaluation/
│ └── evaluate_baseline.py
├── data_quality/ (empty)
├── feature_engineering/ (empty)
├── training/ (empty)
├── inference/ (empty)
├── monitoring/ (empty)
├── data/ (gitignored, .gitkeep preserved)
│ └── raw/
│   ├── customers.csv
│   ├── events.csv
│   ├── events_ground_truth.csv
│   └── baseline_detections.csv (downloaded by evaluate_baseline.py, gitignored)
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
│ └── test_upload_to_volume.py
├── docker/ (empty)
└── .github/
    └── workflows/
        └── ci.yml
```

## Installed Dependencies

**Production** (added `pandas` in Milestone 7):
- `databricks-sdk>=0.133.0`
- `python-dotenv>=1.2.3`
- `pandas` (version per `uv add pandas` resolution — confirm exact pin from
  `pyproject.toml`/`uv.lock`)

**Dev**:
- `pytest>=8.3.0`
- `ruff>=0.6.0`

## Databricks Status
- Edition: Free Edition, serverless compute only (no `persist()`/`cache()`
  support — confirmed during Milestone 5 via `NOT_SUPPORTED_WITH_SERVERLESS`)
- Catalog: `ced`; Schemas: `bronze`, `silver`, `gold`
- Bronze tables: `ced.bronze.customers` (1,000 rows), `ced.bronze.events`
  (27,128 rows)
- Silver tables: `ced.silver.customers` (1,000 valid, 0 rejects),
  `ced.silver.events` (27,128 valid, 0 rejects)
- Gold tables: `ced.gold.customer_events_features` (27,128 rows, exact
  1:1 reconciliation with Silver events, 8 features), `ced.gold.baseline_detections`
  (27,128 rows, new in Milestone 7)
- Gold exports volume: `ced.gold.exports` (new in Milestone 7) — flattened
  CSV export of `baseline_detections` for local evaluation
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — version 3.3.1, `LocalExecutor`, Postgres 16
  backend, 1 temporary smoke-test DAG. Not yet orchestrating any part of this
  project's real pipeline.

## Testing Setup
- Framework: `pytest`
- Current coverage: environment (2), customer generator (7), event generator
  (19), upload-to-volume (3) — **31 total**, unchanged since Milestone 4
- Neither `bronze_ingestion.py`, `silver_transformation.py`,
  `gold_feature_engineering.py`, nor `baseline_detector.py` has automated
  test coverage (Spark/Databricks-only code, no local PySpark harness in
  this project). `evaluate_baseline.py` (local, pure-Python) also has no
  automated test coverage yet — flagged as technical debt #17, not the same
  justification as the Databricks-only notebooks.

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .` — both
  clean as of Milestone 7 changes, confirmed both locally and in CI

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- ✅ Confirmed green on `main` through Milestone 7
- Still does not build/run Docker, Airflow, or touch Databricks (by design — no
  live credentials in CI)

## Commands Used to Verify Milestone 7
```powershell
uv add pandas
uv run ruff check .
uv run ruff format --check .
uv run python evaluation/evaluate_baseline.py
```
(Databricks notebook run manually via "Run All" in the Databricks workspace —
no local execution path, no local PySpark harness.)

Observed output (Databricks notebook, `notebooks/baseline_detector.py`,
Run All, final version after both fixes):
```
OK: 27128 baseline detections reconcile exactly with 27128 Gold rows.
Wrote 27128 rows to ced.gold.baseline_detections

+---------------+-----+
|detection_score|count|
+---------------+-----+
|              0|26589|
|              1|  136|
|              2|  403|
+---------------+-----+

detection_flag = True: 403 (1.49%)

+----------------------+-----+
|rule                  |count|
+----------------------+-----+
|is_new_device         |229  |
|is_unusual_channel    |128  |
|is_unusual_country    |128  |
|amount_deviation_tier1|54   |
|amount_deviation_tier2|46   |
+----------------------+-----+

Exported 27128 rows to /Volumes/ced/gold/exports/baseline_detections.csv
```

Observed output (`evaluation/evaluate_baseline.py`):
```
Downloaded /Volumes/ced/gold/exports/baseline_detections.csv -> data\raw\baseline_detections.csv (1393029 bytes)

=== Overall metrics ===
tp: 403
fp: 0
fn: 139
tn: 26586
precision: 1.0000
recall: 0.7435
f1: 0.8529
false_positive_rate: 0.0000

=== Recall by anomaly_type ===
                   count  caught    recall
anomaly_type
new_device           229     229  1.000000
channel_deviation    128       0  0.000000
geo_deviation        128     128  1.000000
amount_spike          57      46  0.807018
```

---

## Next Recommended Task
**Milestone 8: ML model (baseline → real model)** per the approved
23-milestone roadmap — likely a simple, explainable approach (Isolation
Forest, Logistic Regression, or XGBoost per the project's stated ML scope),
evaluated against the Milestone 7 baseline's precision/recall/F1 as the
reference point to beat, with particular attention to `channel_deviation`
recall given the baseline's structural 0% there. Not started — do not begin
without explicit confirmation.