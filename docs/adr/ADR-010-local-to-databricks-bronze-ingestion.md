# ADR-010: Local-to-Databricks Ingestion Mechanism (Bronze Layer)

## Status
Accepted — implemented and verified in Milestone 4.

## Context
Milestone 3 produces synthetic `customers.csv` and `events.csv` as local files, with
no defined path into Databricks. Databricks Free Edition provides Unity Catalog
(including Volumes), serverless-only compute, and workspace-level REST API/SDK/CLI
access via personal access token — account-level APIs and all-purpose clusters are
not available, but nothing in the workspace-level tooling is blocked.

## Problem
How does locally-generated synthetic data reach Databricks as Delta tables in a way
that is scriptable, reproducible, consistent with the project's existing tooling, and
does not require building real orchestration ahead of the milestone (Milestone 12)
where Airflow is scheduled to get real pipeline logic?

## Options Considered

**A. Manual UI upload** (Databricks "Add or upload data" dialog)
Trivial to do once, zero code. Not reproducible or scriptable; doesn't demonstrate an
engineered ingestion path. Used only as an early sanity check, not as the design.

**B. Databricks CLI (`databricks fs cp`)**
Scriptable via shell, well documented. Introduces a second tool dependency (an
external CLI binary) alongside the project's existing Python-only tooling.

**C. Databricks SDK for Python (`databricks-sdk`), standalone script**
Stays entirely in Python, consistent with the existing generator scripts
(`customer_generator.py`, `event_generator.py`). Directly unit-testable with a mocked
client, no external binary dependency.

**D. Databricks Connect (remote Spark session driven from the local machine)**
Not viable: Free Edition is serverless-only. Also architecturally undesirable even if
it were available — it would blur the Bronze boundary, since transform logic should
execute *inside* Databricks, not be orchestrated line-by-line from a laptop.

## Decision
**Option C.** A standalone Python script, `ingestion/upload_to_volume.py`, uses
`databricks-sdk`'s `WorkspaceClient` to upload the two CSVs to a Unity Catalog volume
(`ced.bronze.raw_uploads`). A separate Databricks-side PySpark notebook,
`notebooks/bronze_ingestion.py` (stored in Databricks' plain-text "source" notebook
format for git-friendliness — see conversation record for the `.py` vs `.ipynb`
reasoning), reads the CSVs from the volume and writes Bronze Delta tables
(`ced.bronze.customers`, `ced.bronze.events`).

`events_ground_truth.csv` is deliberately **not** uploaded — it's an evaluation
artifact, not part of the raw ingestion source, matching the reasoning already
established for keeping it out of `events.csv` in Milestone 3.

### Orchestration timing
This is deliberately **not** wired into Airflow yet. Per existing project tracking,
Airflow does not get real pipeline logic until Milestone 12 — the current DAG is
temporary smoke-test scaffolding. Building real orchestration now would likely mean
reworking it later. Both `upload_file()` and `ingest_to_bronze()` are written with
clean, isolated function boundaries specifically so they can be dropped into an
Airflow `PythonOperator` / `DatabricksSubmitRunOperator` task later without a
redesign.

## Rationale
- Keeps the entire ingestion path in one language, matching the project's existing
  stdlib-first script pattern.
- Avoids introducing orchestration complexity ahead of its scheduled milestone.
- Keeps Bronze's responsibility (land raw data faithfully) cleanly separated from
  Silver's (clean, validate, transform).

## Consequences
- Two new **production** dependencies: `databricks-sdk`, `python-dotenv` — the
  project's first production dependencies (previously dev-only: `pytest`, `ruff`).
- Secrets (PAT, workspace host) live in a git-ignored `.env`, loaded via
  `python-dotenv`; never hardcoded or passed as CLI arguments.
- Bronze writes use `mode("overwrite")`, appropriate because the synthetic datasets
  are full snapshot regenerations each run, not an incremental feed. Trade-off: no
  ingestion history is retained across runs. Revisit if incremental/append semantics
  become relevant in a later milestone.
- CI (`ci.yml`) has no Databricks credentials configured, so the upload script's tests
  mock the SDK client entirely — CI validates script logic (path handling, error
  handling) only, never live connectivity. Live verification is manual, same
  discipline used throughout this project.
- The Bronze notebook has **no automated test coverage**. There is no local PySpark
  test harness in this project (Windows-native, no WSL2; installing local PySpark
  purely for test coverage isn't architecturally justified at this scale).
  Verification is manual: run the notebook, inspect row counts and sample output.

### Known limitation, accepted rather than fixed
Databricks' CSV reader (Photon-accelerated) converts the source generator's
intentional empty-string values (e.g. `merchant_category = ""` for non-monetary event
types) to SQL `NULL` on read. A `nullValue`/`emptyValue` sentinel workaround — which
is documented to work on open-source Spark — was tried and did **not** resolve this
on Databricks' engine. Rather than chase Photon-specific CSV-parsing internals with no
architectural payoff, this is accepted as Bronze's actual behavior. **Silver-layer
cleaning must treat `NULL` `merchant_category` on non-monetary event types
(`login`, `failed_login`, `beneficiary_added`, `device_changed`, `password_changed`,
`profile_changed`) as the expected, valid "not applicable" state — not as missing
data requiring a quality flag.**

This is a deliberate, documented compromise of the "Bronze is a faithful, unopinionated
copy" principle — worth being able to explain in an interview as a concrete example of
a platform-specific data quirk that only surfaces in production-grade tooling (Photon),
not in local development.

## Future Considerations
Databricks Autoloader / Lakeflow Connect could replace the manual volume-upload +
notebook-read pattern with a more production-realistic ingestion mechanism, once
orchestration is properly designed at Milestone 12. Not pursued now — no
architectural need at this data scale, and it would add complexity without
demonstrating a genuinely new concept beyond what Milestone 4 already covers.