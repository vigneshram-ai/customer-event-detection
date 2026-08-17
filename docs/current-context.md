# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestone 1 (repo/environment) and Milestone 2 (synthetic customer generator) are
**complete and verified**. Milestone 3 (synthetic event generator) is now **complete
and verified**. Milestone 4 has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch). CI was last confirmed green
  as of Milestone 1/2 work — **not yet re-confirmed on `main` after Milestone 3**;
  push and check before treating CI as verified for this milestone.
- Local Airflow (Docker Compose, `LocalExecutor`) is running with one manual
  smoke-test DAG. Still no real pipeline logic, and not yet used to orchestrate
  either generator — both are standalone scripts run manually.
- `data_generation/customer_generator.py` (Milestone 2) and
  `data_generation/event_generator.py` (Milestone 3) both exist, are stdlib-only,
  seeded/deterministic, and have full test coverage (28 tests total, all passing).
- A real dataset has been generated and verified: 1,000 customers, 27,128 events,
  542 injected anomalies (2.00%) — files at `data/raw/customers.csv`,
  `data/raw/events.csv`, `data/raw/events_ground_truth.csv`.
- No Spark, no Databricks, no MLflow, no models, no Delta tables exist yet. No
  ingestion/orchestration pipeline exists yet — the generators are not wired into
  Airflow or any Bronze-layer process.
- `pyproject.toml` has zero production dependencies. Only `pytest` and `ruff`.

## Key Design Decisions From Milestone 3 (do not silently revisit)
- Ground truth anomaly labels live in a **separate sidecar file**
  (`events_ground_truth.csv`), not inline in `events.csv` — keeps the main event file
  representative of an unlabeled real ingestion source.
- Default event-generation date window is a **fixed literal range**
  (`2026-01-01`–`2026-03-31`), not `datetime.now()` — required for deterministic,
  reproducible output given the same seed.
- Anomaly type selection is weighted by `event_type`: `new_device` is impossible for
  `device_changed` events (self-contradictory) and boosted for
  `login`/`card_transaction`/`payment` (device is the actual acting agent for those).
- Event volume per customer uses a flat configurable range (`--events-min`/`--events-max`),
  **not** tied to `account_age_days` tier — user explicitly chose the simpler option;
  revisit later if needed.
- Default anomaly injection rate is 2% (rare-event realistic), configurable via
  `--anomaly-rate`.

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11.16 (confirmed via pytest platform output)
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected
- Git version 2.55.0.windows.4

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written — only the
  narrower executor/version decision is documented (ADR-009).
- **How local CSV output reaches Databricks/Delta is undesigned.** Discussed
  conceptually (likely: Airflow task uploads to a Databricks Unity Catalog volume via
  REST API/SDK, then a Databricks job lands it as Delta) but not decided or
  implemented. This must be properly designed — with trade-offs presented — before
  Milestone 4 (Bronze ingestion) begins. Do not assume a specific mechanism.
- Anomaly injection is single-event-level only; no multi-event bursts. Deliberate
  Milestone 3 scope decision, documented as technical debt, not silently expanded.
- CI has not been re-confirmed green after Milestone 3's changes.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and verified with
  observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Every technology must have a stated architectural purpose — no CV-padding.
- Claude Desktop workflow: never assume direct local file/execution access — provide
  files and exact commands, wait for the user to run them and report output.

## Immediate Next Step
Push Milestone 3 changes and confirm CI is green on `main`. Then start Milestone 4:
**Bronze-layer ingestion into Databricks/Delta** — this requires first explaining and
designing the local→Databricks handoff mechanism (currently undesigned) before any
implementation, per the standard explain → design → implement flow. Do not begin
without explicit user confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009-airflow-local-dev-topology.md` — Airflow version/executor decision
- `README.md` — public-facing summary (kept minimal, accurate)