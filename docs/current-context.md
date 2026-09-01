# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–4 are **complete and verified**. Milestone 4 (Bronze-layer ingestion
into Databricks/Delta) closed with one documented, accepted known limitation (see
below). Milestone 5 has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- **CI is confirmed green on `main`** after Milestone 4's changes. One lint fix was
  needed along the way: `ruff` flagged `spark`/`display` as undefined names in
  `notebooks/bronze_ingestion.py` (they're Databricks-runtime-injected globals, not
  real imports). Fixed with `from databricks.sdk.runtime import display, spark` —
  Databricks' own documented pattern for this, doesn't create a second Spark
  session at runtime. Notebook re-verified after the fix with identical output.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with only the
  temporary smoke-test DAG. Not orchestrating anything real yet — deliberately
  deferred to Milestone 12.
- `data_generation/customer_generator.py`, `data_generation/event_generator.py`,
  `ingestion/upload_to_volume.py` all exist, are tested (31 tests total, all
  passing), `ruff` clean.
- `notebooks/bronze_ingestion.py` exists and has been run successfully against the
  live Databricks Free Edition workspace. It has **no automated test coverage** —
  verification is manual/observed-output only (no local PySpark harness in this
  project).
- **Databricks side is real and verified**: workspace
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`, Unity Catalog `ced`, schema
  `bronze`, volume `raw_uploads` (holds `customers.csv`, `events.csv` — NOT the
  ground-truth sidecar, deliberately excluded). Delta tables `ced.bronze.customers`
  (1,000 rows) and `ced.bronze.events` (27,128 rows) exist and match the Milestone 3
  generator output exactly.
- No Silver/Gold layers, no feature engineering, no MLflow, no models exist yet.
- `pyproject.toml` now has **two production dependencies**: `databricks-sdk`,
  `python-dotenv` (first production deps in the project — previously dev-only).
- `.env` (git-ignored, confirmed via `git status`) holds `DATABRICKS_HOST` /
  `DATABRICKS_TOKEN`. Never commit this file or its contents.

## Key Design Decisions From Milestone 4 (do not silently revisit — full detail in ADR-010)
- Local→Databricks handoff: standalone Python script using `databricks-sdk`
  (`WorkspaceClient`), NOT the Databricks CLI, NOT Databricks Connect.
- NOT wired into Airflow yet — deliberate, deferred to Milestone 12 when Airflow
  gets real pipeline logic. Both `upload_file()` and `ingest_to_bronze()` are
  written with clean function boundaries so they drop into Airflow tasks later
  without redesign.
- Databricks notebooks are stored as plain `.py` files in Databricks' "source"
  format (not `.ipynb`) — git-diff friendly, lintable by `ruff`, consistent with
  the project's all-Python convention.
- Bronze schema is explicit (`StructType`), not inferred. `event_timestamp` is kept
  as a string in Bronze — parsing to a real timestamp is a Silver-layer decision.
- Bronze writes use `mode("overwrite")` — full snapshot semantics, matching how the
  generators work (regenerate the whole dataset each run). No ingestion history is
  retained across runs.
- **`merchant_category` NULL-vs-empty-string caveat, accepted not fixed**:
  Databricks' Photon CSV reader converts the generator's intentional `""` values
  (non-monetary event types) to `NULL`. A sentinel-based `nullValue`/`emptyValue`
  workaround was investigated and does not work on this engine. This is Bronze's
  actual, accepted behavior. **Silver-layer cleaning MUST treat `NULL`
  `merchant_category` on non-monetary event types (`login`, `failed_login`,
  `beneficiary_added`, `device_changed`, `password_changed`, `profile_changed`) as
  the expected "not applicable" state — not as missing/dirty data.** Do not
  silently "fix" this in Bronze later without discussing it first; it's a
  documented trade-off, not an oversight.
- Unity Catalog catalog name is lowercase `ced`, not `CED` — UC normalizes catalog
  names to lowercase regardless of how they're typed at creation. Both
  `upload_to_volume.py`'s default `--volume-path` and the notebook's `CATALOG`
  constant use lowercase `ced`.

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace:
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schema `bronze`, volume `raw_uploads`
- PAT stored in `.env` (git-ignored)

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written.
- **Silver-layer design is not started.** Must explicitly resolve the
  `merchant_category` NULL-handling rule (see above), define real data-quality
  gates (nulls, valid event types/timestamps/amount ranges, referential integrity
  to `customers`), and decide how/where `event_timestamp` gets parsed to a proper
  timestamp type.
- CI has not been re-confirmed green after Milestone 4's changes.
- Bronze ingestion is manual (no Airflow orchestration) — deliberate, per ADR-010,
  until Milestone 12.

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
- When something goes wrong (e.g. the CSV null/empty investigation), don't chase
  it indefinitely if the user says stop — accept and document the decision
  explicitly rather than silently working around it later.

## Immediate Next Step
Milestone 4 is fully closed — CI confirmed green, all output verified. Next up is
**Milestone 5: Silver-layer cleaning and validation** — this requires first explicitly
designing: (1) the `merchant_category` NULL-handling rule, (2) the real
data-quality gates to apply, (3) where/how `event_timestamp` gets parsed, and (4)
referential integrity checks between `events` and `customers`. Do not begin without
explicit user confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009-airflow-local-dev-topology.md` — Airflow version/executor decision
- `docs/adr/ADR-010-local-to-databricks-bronze-ingestion.md` — ingestion mechanism,
  Bronze design, and the merchant_category NULL-caveat decision
- `README.md` — public-facing summary (kept minimal, accurate)