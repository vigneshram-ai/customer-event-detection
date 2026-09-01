# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–5 are **complete and verified**. Milestone 5 (Silver-layer cleaning and
validation) closed with one deliberate technical-debt trade-off (see below). CI has
not yet been re-confirmed green on `main` after Milestone 5's changes — only local
`ruff check`/`ruff format --check` are confirmed clean so far. Milestone 6 has **not**
started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI was confirmed green on `main` as of Milestone 4. **Not yet re-confirmed for
  Milestone 5** — push and confirm before treating Milestone 5 as fully closed for
  CI purposes.
- Local Airflow (Docker Compose, `LocalExecutor`) is still running with only the
  temporary smoke-test DAG. Not orchestrating anything real yet — deliberately
  deferred to Milestone 12.
- `data_generation/customer_generator.py`, `data_generation/event_generator.py`,
  `ingestion/upload_to_volume.py` all exist, are tested (31 tests total, all
  passing), `ruff` clean.
- `notebooks/bronze_ingestion.py` and `notebooks/silver_transformation.py` both
  exist and have been run successfully against the live Databricks Free Edition
  workspace. **Neither has automated test coverage** — verification is
  manual/observed-output only (no local PySpark harness in this project).
- **Databricks side is real and verified**: workspace
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`, Unity Catalog `ced`.
  - `ced.bronze.customers` (1,000 rows), `ced.bronze.events` (27,128 rows)
  - `ced.silver.customers` (1,000 valid, 0 rejects), `ced.silver.events`
    (27,128 valid, 0 rejects)
  - Volume `ced.bronze.raw_uploads` holds `customers.csv`, `events.csv` — NOT the
    ground-truth sidecar, deliberately excluded.
- Compute is **serverless only** (Free Edition) — confirmed during Milestone 5 that
  `.persist()`/`.cache()` are unsupported (`NOT_SUPPORTED_WITH_SERVERLESS`). No
  persistent executor memory to pin DataFrames into.
- No Gold layer, no feature engineering, no MLflow, no models exist yet.
- `pyproject.toml` has two production dependencies (unchanged since Milestone 4):
  `databricks-sdk`, `python-dotenv`.
- `.env` (git-ignored, confirmed via `git status`) holds `DATABRICKS_HOST` /
  `DATABRICKS_TOKEN`. Never commit this file or its contents.

## Key Design Decisions From Milestone 5 (do not silently revisit — full detail in ADR-011)
- Silver validation logic is **plain PySpark** (`filter`, `isNull`, `when`/
  `otherwise`, window functions) — not Great Expectations, not Pandera, not Delta
  Live Tables expectations. Consistent with Bronze's manual-check style; avoids a
  second validation framework and avoids preempting the Airflow orchestration
  planned for Milestone 12 (DLT would introduce a competing orchestrator).
- Failure handling is **quarantine**, not hard-fail or silent drop: every Bronze
  row lands in exactly one of `ced.silver.<table>` (valid) or
  `ced.silver.<table>_rejects` (failed, with `_rejection_reasons` array). Row
  counts are programmatically reconciled on every write
  (`valid + rejects == bronze_input_count`).
- **Honest limitation**: quarantine is an enforcement/audit point, not a pipeline
  circuit-breaker — there is no orchestrator yet to actually halt downstream
  processing on a bad batch. That's a Milestone 12 concern.
- Customers are validated and split **before** events; events' referential-
  integrity check uses the cleaned Silver `customers` set, not raw Bronze — an
  event referencing an already-rejected customer is itself rejected.
- `event_timestamp` parsed from Bronze's `StringType` to `TimestampType` using an
  **explicitly pinned format** (`yyyy-MM-dd'T'HH:mm:ss`), confirmed against the
  generator's actual `datetime.isoformat()` output — not relying on
  `to_timestamp()`'s auto-detection, so future format drift fails loudly (as
  rejects) instead of silently.
- **`merchant_category` NULL caveat from ADR-010 resolved**: NULL is valid/expected
  for the 6 non-monetary event types; only flagged when NULL on a monetary event
  type (`card_transaction`/`payment`/`transfer`).
- **New caveat introduced — `amount = 0.0` for non-monetary events**: the M3
  generator writes a literal `0.0` (not NULL/blank) as its default for non-monetary
  `amount`, unlike `merchant_category`'s correct NULL default. First surfaced as a
  34.92% reject rate (9,473/27,128 events), confirmed via raw CSV inspection
  (literal `0`, not blank) before deciding a fix. **Deliberately resolved by
  relaxing the Silver rule to accept `0.0`** as the valid non-monetary sentinel,
  rather than regenerating Milestone 3 data. Consequence: "not applicable" and
  "genuinely zero" are indistinguishable for `amount` from Silver onward. Any
  *other* non-zero value on a non-monetary event is still correctly flagged. Do
  not silently "fix" this by touching `event_generator.py` later without
  discussing it first — it's a documented trade-off, not an oversight. Full
  rationale in ADR-011.
- `.cache()`/`.persist()` are **not available** on Databricks Free Edition
  serverless compute — removed from `silver_transformation.py` after a live
  `NOT_SUPPORTED_WITH_SERVERLESS` error. Not architecturally significant here
  (the cached DataFrame was only consumed once), but worth remembering for any
  future notebook code on this workspace.

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze` and `silver`, volume
  `bronze.raw_uploads`
- PAT stored in `.env` (git-ignored)

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written.
- **CI has not been re-confirmed green after Milestone 5's changes.** Push and
  confirm before starting Milestone 6.
- **Gold-layer / feature engineering design is not started.**
- `amount = 0.0` ambiguity (see above) — intentionally left as-is; only revisit if
  Milestone 6+ feature engineering genuinely needs to distinguish "not applicable"
  from "zero."
- Bronze and Silver ingestion are both manual (no Airflow orchestration) —
  deliberate, per ADR-010/ADR-011, until Milestone 12.

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
- When something goes wrong (e.g. the `amount = 0.0` investigation), don't chase
  it indefinitely if the user picks a pragmatic resolution — accept and document
  the trade-off explicitly rather than silently reopening it later.

## Immediate Next Step
Push Milestone 5 and confirm CI is green on `main`. Then start **Milestone 6:
Gold-layer feature engineering** — not started; do not begin without explicit user
confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009-airflow-local-dev-topology.md` — Airflow version/executor decision
- `docs/adr/ADR-010-local-to-databricks-bronze-ingestion.md` — ingestion mechanism,
  Bronze design, and the merchant_category NULL-caveat decision
- `docs/adr/ADR-011-silver-data-quality-strategy.md` — Silver validation mechanism,
  quarantine strategy, and the amount NULL-vs-0.0 technical debt decision
- `README.md` — public-facing summary (kept minimal, accurate)