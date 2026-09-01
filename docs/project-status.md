# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 5_

_Milestone 5 status: IMPLEMENTED AND VERIFIED — fully closed, CI green, real
end-to-end run against live Databricks confirmed 0% reject rate on both tables.
One deliberate technical-debt trade-off documented (amount NULL-vs-0.0, see
ADR-011)._

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
  to Silver (resolved in Milestone 5 — see below).
- First production dependencies added: `databricks-sdk`, `python-dotenv`. Secrets
  in git-ignored `.env`.
- Full test suite: 31 passed, `ruff check`/`ruff format --check` clean, CI
  confirmed green on `main` (after a `spark`/`display` lint fix — Databricks
  runtime globals resolved via `from databricks.sdk.runtime import display, spark`).

**Milestone 5 — Silver-layer cleaning and validation**
- **Design decisions resolved and documented in ADR-011**: validation mechanism
  (PySpark-native, not Great Expectations/Pandera/DLT expectations) and failure
  handling (quarantine to a `_rejects` table, not hard-fail or silent drop).
- `notebooks/silver_transformation.py` — new Databricks notebook, same
  plain-text "source" format and `CATALOG`/audit-column conventions as Bronze.
  - `validate_customers()`: required-field null checks, `account_age_days >= 0`,
    `customer_id` uniqueness (window function).
  - `validate_events()`: required-field null checks, `event_type` enum validation
    against the 9 known values, `event_timestamp` parsed from `StringType` to
    `TimestampType` using an explicitly pinned format (`yyyy-MM-dd'T'HH:mm:ss`,
    matching the generator's confirmed `datetime.isoformat()` output — pinned
    rather than relying on auto-detection so a future format drift fails loudly
    as rejects, not silently), `amount` consistency rules (see technical debt
    below), `merchant_category` required only for monetary event types,
    `event_id` uniqueness, and referential integrity against the *cleaned* Silver
    `customers` set (not raw Bronze — an event referencing an already-rejected
    customer is itself rejected).
  - Every row lands in exactly one of `<table>` or `<table>_rejects`; each write
    reconciles `valid_count + rejects_count == bronze_input_count` and raises if
    they don't match.
  - `_rejection_reasons` is an array per row (a row can fail multiple rules at
    once) plus a `_validated_at` audit timestamp.
- **`merchant_category` NULL caveat from ADR-010 formally resolved**: NULL is
  valid/expected for the 6 non-monetary event types; only flagged when NULL on a
  monetary event type.
- **New issue found and resolved during verification**: the M3 generator writes a
  literal `0.0` (not NULL/blank) as its default `amount` for non-monetary events —
  first surfaced as a 34.92% reject rate (9,473 of 27,128 events) all rejected
  for `amount_present_for_non_monetary_event`. Confirmed via raw CSV inspection
  (literal `0` in the file, not blank) before deciding a fix. Resolved by
  **relaxing the Silver rule to accept `0.0`** as the valid non-monetary sentinel,
  rather than regenerating M3 data — a deliberate trade-off, not a silent patch.
  Full rationale and consequences in ADR-011.
- One implementation fix during development: `silver_customers.cache()` was
  removed after Databricks raised `NOT_SUPPORTED_WITH_SERVERLESS` —
  `persist()`/`cache()` isn't available on serverless compute (no persistent
  executor memory to pin into). Not architecturally significant — the DataFrame
  was only consumed once, so caching bought nothing anyway.
- **Real end-to-end run verified** against live Databricks after the `amount` fix:
  - `ced.silver.customers` — 1,000 valid, 0 rejected (0.00%)
  - `ced.silver.events` — 27,128 valid, 0 rejected (0.00%)
  - Rejection-reason breakdown queries confirmed empty for both tables.
- `uv run ruff check .` / `uv run ruff format --check .` — both clean (user-confirmed).
- No automated test coverage for `silver_transformation.py`, consistent with
  Bronze — Databricks/Spark-only code, no local PySpark harness in this project.

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
  Only the narrower executor/version decision (ADR-009) and the ingestion
  mechanism decisions (ADR-010, ADR-011) exist.

### ⏳ Future
- Everything from Milestone 6 onward (Gold layer, feature engineering, MLflow,
  batch inference, monitoring, security, full CI/CD, Airflow real orchestration at
  Milestone 12).

---

## Current Work
None in progress. Milestone 5 is closed.

## Pending Work
Milestones 6–23 per the approved roadmap, starting with Gold-layer feature
engineering.

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
| `uv` over Poetry/pip | Recorded here only — tooling preference |
| `ruff` for lint + format (single tool) | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV | Recorded here only (Milestone 3) |
| Fixed literal default date window for event generation | Recorded here only (Milestone 3) |
| Anomaly type selection weighted by event_type | Recorded here only (Milestone 3) |

Full ADR-002 ("Airflow as the Orchestration Layer" broadly) remains pending.

---

## Known Issues
- None blocking. CI confirmed green on `main` after Milestone 5 changes.

## Technical Debt
1. No pre-commit hook. Flagged since Milestone 1, still low priority.
2. CI does not validate the Airflow Docker Compose stack (deliberate, revisit once
   a real DAG exists at Milestone 12).
3. The Airflow smoke-test DAG (`00_environment_smoke_test.py`) is temporary
   scaffolding; removal scheduled for Milestone 12.
4. Anomaly injection is single-event-level only (Milestone 3 scope decision).
5. Only `new_device` anomaly type has event-type-aware logic (Milestone 3 scope
   decision).
6. Bronze ingestion is not yet orchestrated by Airflow — both `upload_to_volume.py`
   and `bronze_ingestion.py` are run manually. Deliberate, deferred to Milestone 12
   per ADR-010.
7. Bronze writes use `overwrite`, not `append` — no ingestion history is retained
   across repeated runs. Acceptable at current scope; revisit if incremental
   semantics become relevant.
8. **New**: `amount = 0.0` is indistinguishable from a genuinely zero-value
   monetary transaction for non-monetary event types, from Silver onward. Root
   cause is the M3 generator's default value choice (`0.0`, not `None`), not a
   Silver bug. Deliberately not fixed at the source to avoid reopening a verified
   milestone. Revisit by fixing `event_generator.py` if Milestone 6+ feature
   engineering (e.g. `amount_spike` detection) needs the distinction. Full
   rationale in ADR-011.
9. **New**: Silver ingestion is not yet orchestrated by Airflow — same deferral as
   Bronze, per Milestone 12.
10. **New**: `silver_transformation.py` has no automated test coverage, same
    reasoning as `bronze_ingestion.py` (Databricks/Spark-only code, no local
    PySpark harness in this project).

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
| Unity Catalog schemas | `ced.bronze`, `ced.silver` | ✅ Verified |
| Unity Catalog volume | `ced.bronze.raw_uploads` | ✅ Verified |

## Repository Structure (as of Milestone 5)
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
│ │ └── ADR-011-silver-data-quality-strategy.md
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
│ └── silver_transformation.py
├── data_quality/ (empty)
├── feature_engineering/ (empty)
├── training/ (empty)
├── inference/ (empty)
├── monitoring/ (empty)
├── data/ (gitignored, .gitkeep preserved)
│ └── raw/
│   ├── customers.csv
│   ├── events.csv
│   └── events_ground_truth.csv
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

**Production** (unchanged since Milestone 4):
- `databricks-sdk>=0.133.0`
- `python-dotenv>=1.2.3`

**Dev**:
- `pytest>=8.3.0`
- `ruff>=0.6.0`

## Databricks Status
- Edition: Free Edition, serverless compute only (no `persist()`/`cache()`
  support — confirmed during Milestone 5 via `NOT_SUPPORTED_WITH_SERVERLESS`)
- Catalog: `ced`; Schemas: `bronze`, `silver`
- Bronze tables: `ced.bronze.customers` (1,000 rows), `ced.bronze.events`
  (27,128 rows)
- Silver tables: `ced.silver.customers` (1,000 valid, 0 rejects),
  `ced.silver.events` (27,128 valid, 0 rejects)
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — version 3.3.1, `LocalExecutor`, Postgres 16
  backend, 1 temporary smoke-test DAG. Not yet orchestrating any part of this
  project's real pipeline.

## Testing Setup
- Framework: `pytest`
- Current coverage: environment (2), customer generator (7), event generator
  (19), upload-to-volume (3) — **31 total**, unchanged since Milestone 4
- Neither `bronze_ingestion.py` nor `silver_transformation.py` has automated test
  coverage (Spark/Databricks-only code, no local PySpark harness in this project)

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .` — both
  clean as of Milestone 5 changes, confirmed both locally and in CI

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- ✅ **Confirmed green on `main` after Milestone 5 changes**
- Still does not build/run Docker, Airflow, or touch Databricks (by design — no
  live credentials in CI)

## Commands Used to Verify Milestone 5
```powershell
uv run ruff check .
uv run ruff format --check .
```
(Databricks notebook run manually via "Run All" in the Databricks workspace —
no local execution path, no local PySpark harness.)

Observed output (Databricks notebook, `notebooks/silver_transformation.py`, Run All,
after the `amount = 0.0` rule fix):
```
OK: ced.silver.customers -- 1,000 valid, ced.silver.customers_rejects -- 0 rejected (0.00% reject rate)
OK: ced.silver.events -- 27,128 valid, ced.silver.events_rejects -- 0 rejected (0.00% reject rate)
```
Rejection-reason breakdown queries for both `events_rejects` and
`customers_rejects` returned zero rows.

---

## Next Recommended Task
**Milestone 6: Gold-layer feature engineering.** Not started — do not begin
without explicit confirmation.