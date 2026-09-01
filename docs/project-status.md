# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 4_

_Milestone 4 status: IMPLEMENTED AND VERIFIED (with one documented known limitation)_

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
- **Design decision resolved and documented**: local→Databricks handoff mechanism
  (flagged as undesigned at end of Milestone 3) is now designed, implemented, and
  recorded in **ADR-010**.
- `ingestion/upload_to_volume.py` (new package `ingestion/`) — standalone Python
  script using `databricks-sdk`'s `WorkspaceClient` to upload `customers.csv` and
  `events.csv` to the `ced.bronze.raw_uploads` Unity Catalog volume. Deliberately
  excludes `events_ground_truth.csv` (evaluation artifact, not raw ingestion source —
  same reasoning as the Milestone 3 sidecar decision).
  - Validates local file exists and is non-empty before attempting upload.
  - Uses `overwrite=True` on the SDK upload call — reruns are safe.
  - 3 tests, all mocking the Databricks SDK client (no live credentials in CI — see
    ADR-010 consequences).
- `notebooks/bronze_ingestion.py` — Databricks notebook, stored in Databricks'
  plain-text "source" format (not `.ipynb`) for git-friendly diffs and consistency
  with the project's all-Python convention (rationale: see ADR-010).
  - Explicit `StructType` schemas for both tables (no schema inference).
  - `event_timestamp` kept as `StringType` in Bronze — parsing deferred to Silver.
  - Header-validation gate (`_validate_header`) — fails fast if the CSV's actual
    header doesn't match the expected column list, since Spark maps an
    explicitly-supplied schema **positionally**, not by column name.
  - Row-count integrity check after write (read count must equal written Delta
    table count).
  - Audit columns `_ingested_at` (timestamp) and `_source_file` (string) added on
    write.
  - Writes use `mode("overwrite")` — full snapshot regeneration semantics, not
    incremental (see ADR-010 consequences for the trade-off).
- **Real end-to-end run verified** against the live Databricks Free Edition
  workspace: `ced.bronze.customers` — 1,000 rows; `ced.bronze.events` — 27,128 rows.
  Both counts match the Milestone 3 generator output exactly. Sample query
  (`SELECT * ... LIMIT 5`) confirmed audit columns populated and no column
  misalignment.
- **Known limitation, investigated and accepted (not fixed)**: Databricks' CSV
  reader (Photon-accelerated) converts the generator's intentional empty-string
  values (e.g. `merchant_category = ""` on non-monetary event types) to SQL `NULL`
  on read. A `nullValue`/`emptyValue` sentinel workaround — documented to work on
  open-source Spark — did not resolve this on Databricks' engine. Full
  investigation and decision recorded in **ADR-010**. Silver-layer cleaning must
  treat `NULL` `merchant_category` on non-monetary event types as the expected
  "not applicable" state, not as missing data.
- Two new **production** dependencies added: `databricks-sdk>=0.133.0`,
  `python-dotenv>=1.2.3` — the project's first production dependencies (previously
  dev-only: `pytest`, `ruff`).
- Secrets handling: `.env` (git-ignored, confirmed via `git status`) holds
  `DATABRICKS_HOST` / `DATABRICKS_TOKEN`, loaded via `python-dotenv`. Never
  hardcoded, never passed as CLI arguments.

Full test suite: **31 passed** (28 from Milestones 1–3 + 3 new for
`upload_to_volume.py`), `ruff check` and `ruff format --check` both clean.

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002) — still not formally written.
  Only the narrower executor/version decision (ADR-009) and the ingestion mechanism
  decision (ADR-010) exist.
- Silver-layer cleaning/validation logic — not yet designed. Must resolve the
  `merchant_category` NULL-handling rule (see above) as part of that design.

### ⏳ Future
- Everything from Milestone 5 onward (Silver/Gold, feature engineering, MLflow,
  batch inference, monitoring, security, full CI/CD, Airflow real orchestration at
  Milestone 12).

---

## Current Work
None in progress. Milestone 4 is closed.

## Pending Work
Milestones 5–23 per the approved roadmap, starting with Silver-layer cleaning and
validation.

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor` (not Celery) for local development | **ADR-009** |
| Local→Databricks ingestion via `databricks-sdk` standalone script + Databricks notebook (not CLI, not Airflow-wired yet, not Databricks Connect) | **ADR-010** |
| Bronze writes use `mode("overwrite")`, not append | **ADR-010** (consequences) |
| `merchant_category` NULL-on-read caveat accepted as Bronze behavior, deferred to Silver | **ADR-010** (known limitation) |
| Databricks notebooks stored as `.py` "source" format, not `.ipynb` | Recorded here + ADR-010 — git-diff friendliness, lintability, consistency with all-Python repo convention |
| `uv` over Poetry/pip | Recorded here only — tooling preference |
| `ruff` for lint + format (single tool) | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV | Recorded here only (Milestone 3) |
| Fixed literal default date window for event generation | Recorded here only (Milestone 3) |
| Anomaly type selection weighted by event_type | Recorded here only (Milestone 3) |

Full ADR-002 ("Airflow as the Orchestration Layer" broadly) remains pending.

---

## Known Issues
- **`merchant_category` reads as `NULL` instead of empty string for non-monetary
  event types in Bronze** (Databricks Photon CSV reader behavior). Documented and
  accepted in ADR-010. Silver-layer cleaning must handle this explicitly.
- CI has not been re-confirmed green on `main` after Milestone 4's changes — **push
  and confirm before treating Milestone 4 as fully closed for CI purposes.**

## Technical Debt
1. No pre-commit hook. Flagged since Milestone 1, still low priority.
2. CI does not validate the Airflow Docker Compose stack (deliberate, revisit once a
   real DAG exists at Milestone 12).
3. The Airflow smoke-test DAG (`00_environment_smoke_test.py`) is temporary
   scaffolding; removal scheduled for Milestone 12.
4. Anomaly injection is single-event-level only (Milestone 3 scope decision).
5. Only `new_device` anomaly type has event-type-aware logic (Milestone 3 scope
   decision).
6. **New**: `merchant_category` NULL-vs-empty-string caveat (see Known Issues above)
   — must be resolved in Silver-layer design, not silently patched later.
7. **New**: Bronze ingestion is not yet orchestrated by Airflow — both
   `upload_to_volume.py` and `bronze_ingestion.py` are run manually. Deliberate,
   deferred to Milestone 12 per ADR-010.
8. **New**: Bronze writes use `overwrite`, not `append` — no ingestion history is
   retained across repeated runs. Acceptable at current scope; revisit if
   incremental semantics become relevant.

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
| Databricks workspace | Free Edition, `https://dbc-01205ae9-f87b.cloud.databricks.com/` | ✅ Verified (live upload + notebook run succeeded) |
| Unity Catalog catalog | `ced` (lowercase — UC normalizes catalog names) | ✅ Verified |
| Unity Catalog schema | `ced.bronze` | ✅ Verified |
| Unity Catalog volume | `ced.bronze.raw_uploads` | ✅ Verified |

## Repository Structure (as of Milestone 4)
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
│ │ └── ADR-010-local-to-databricks-bronze-ingestion.md
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
│ └── bronze_ingestion.py
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

**Production** (new as of Milestone 4):
- `databricks-sdk>=0.133.0`
- `python-dotenv>=1.2.3`

**Dev**:
- `pytest>=8.3.0`
- `ruff>=0.6.0`

## Databricks Status (New — Milestone 4)
- Edition: Free Edition, serverless compute only
- Catalog: `ced`; Schema: `bronze`; Volume: `raw_uploads`
- Tables: `ced.bronze.customers` (1,000 rows), `ced.bronze.events` (27,128 rows)
- Notebook execution: manual (Run All), not yet orchestrated

## Airflow Status
- Unchanged since Milestone 1/3 — version 3.3.1, `LocalExecutor`, Postgres 16
  backend, 1 temporary smoke-test DAG. Not yet orchestrating any part of this
  project's real pipeline.

## Testing Setup
- Framework: `pytest`
- Current coverage: environment (2), customer generator (7), event generator (19),
  upload-to-volume (3) — **31 total**
- Note: `notebooks/bronze_ingestion.py` has no automated test coverage (Spark/
  Databricks-only code, no local PySpark harness in this project — see ADR-010).

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .` — both
  clean as of Milestone 4 changes

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- **Not yet re-confirmed green on `main` after Milestone 4 changes** — push and
  confirm before considering Milestone 4 fully closed for CI purposes
- Still does not build/run Docker, Airflow, or touch Databricks (by design — no
  live credentials in CI)

## Commands Used to Verify Milestone 4
```powershell
uv add databricks-sdk
uv add python-dotenv
uv run ruff check .
uv run ruff format --check .
uv run pytest -v
uv run python ingestion/upload_to_volume.py
```

Observed output (local):
```
31 passed in 20.94s
Uploading data\raw\customers.csv -> /Volumes/ced/bronze/raw_uploads/customers.csv
  OK (43,555 bytes)
Uploading data\raw\events.csv -> /Volumes/ced/bronze/raw_uploads/events.csv
  OK (2,961,320 bytes)
Upload complete.
```

Observed output (Databricks notebook, `notebooks/bronze_ingestion.py`, Run All):
```
OK: ced.bronze.customers -- 1,000 rows
OK: ced.bronze.events -- 27,128 rows
```
`SELECT COUNT(*)` on both tables confirmed matching counts. `SELECT * LIMIT 5` on
`events` confirmed `_ingested_at`/`_source_file` populated and no column
misalignment (aside from the documented `merchant_category` NULL caveat).

---

## Next Recommended Task
**Milestone 5: Silver-layer cleaning and validation.** Must resolve, as part of
design (not silently): the `merchant_category` NULL-handling rule for non-monetary
event types (per ADR-010), real data-quality gates (nulls, valid event types, valid
timestamps, valid amount ranges, referential integrity between `events` and
`customers`), and parsing `event_timestamp` from string to a proper timestamp type.
Not started — do not begin without explicit confirmation.