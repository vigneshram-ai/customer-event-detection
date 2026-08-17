# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 3_

_Milestone 3 status: IMPLEMENTED AND VERIFIED_

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
- `data_generation/event_generator.py` (stdlib only) — reads the Milestone 2 customer
  population from CSV (decoupled interface, no shared in-memory objects between
  generators) and produces a temporal event stream per customer.
- Event schema: `event_id, customer_id, event_timestamp, event_type, amount, currency,
  country, channel, device_id, merchant_category, authentication_status`.
- 9 weighted `event_type` values (`card_transaction`, `login`, `payment`, `transfer`,
  `failed_login`, `beneficiary_added`, `device_changed`, `password_changed`,
  `profile_changed`), each with realistic field population rules (monetary fields only
  for `card_transaction`/`payment`/`transfer`; `authentication_status` only varies for
  `login`/`failed_login`).
- Per-customer baseline spend amount (drawn once per customer) so amount deviations
  are relative to each customer's own norm, not a global average — required for the
  planned "amount deviation from historical behaviour" feature later in the roadmap.
- Anomaly injection: 4 anomaly types (`new_device`, `geo_deviation`,
  `channel_deviation`, `amount_spike`), layered onto a normally-generated event at a
  configurable rate (`--anomaly-rate`, default 2%).
  - `new_device` is structurally excluded for `device_changed` events (self-contradictory)
    and boosted (weight 0.55 vs. base 0.25) for `login`/`card_transaction`/`payment`,
    where a device is the actual acting agent.
  - `amount_spike` is only selectable for monetary event types.
- Ground truth (`is_synthetic_anomaly`, `anomaly_type`) written to a **separate sidecar
  file** (`events_ground_truth.csv`, keyed by `event_id`), not inlined into `events.csv`
  — deliberate design choice so the main event file stays representative of an
  unlabeled real ingestion source, while still enabling future precision/recall
  evaluation against known truth.
- Determinism: fixed default date window (`2026-01-01` to `2026-03-31`, not
  `datetime.now()`) so `(customers_file, seed, date range)` always reproduces
  identical output — `datetime.now()` would have silently broken the reproducibility
  principle established in Milestone 2.
- 19 tests passing (determinism, schema shape, profile-consistency for normal events,
  deviation-correctness for each anomaly type, the two anomaly-weighting fixes above,
  edge cases/validation, CSV round-trip).
- **Real end-to-end run verified**: 1,000 customers → 27,128 events, 542 anomalies
  injected (2.00%, matching the configured `--anomaly-rate`).
- Output: `data/raw/events.csv`, `data/raw/events_ground_truth.csv`.

Full test suite: **28 passed** (7 Milestone 2 + 2 Milestone 1 environment + 19
Milestone 3), `ruff check` and `ruff format --check` both clean.

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (ADR-002, broader Airflow vs.
  cron/Dagster/Prefect/plain scripts) — still not formally written. Only the
  narrower executor/version decision is documented (ADR-009).
- How local CSV output will reach Databricks Delta (Bronze layer). Discussed
  conceptually with the user (likely path: Airflow task uploads to a Databricks
  Unity Catalog volume via REST API/SDK, then a Databricks job lands it as Delta) —
  **not decided or implemented**. Will be properly designed and become its own ADR
  when the Bronze ingestion milestone begins.

### ⏳ Future
- Everything from Milestone 4 onward (Bronze/Silver/Gold, Databricks/PySpark,
  MLflow, batch inference, monitoring, security, full CI/CD).

---

## Current Work
None in progress. Milestone 3 is closed.

## Pending Work
Milestones 4–23 per the approved roadmap, starting with Bronze-layer ingestion into
Databricks/Delta.

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor` (not Celery) for local development | **ADR-009** |
| `uv` over Poetry/pip | Recorded here only — tooling preference, not architecturally significant |
| `ruff` for lint + format (single tool) | Recorded here only — same reasoning |
| No Makefile; direct `uv`/`docker compose` commands | Recorded here only |
| Ground-truth anomaly labels in a separate sidecar CSV, not inline in `events.csv` | Recorded here only — data-generation design choice, not a full ADR-level system trade-off. Rationale: keeps `events.csv` representative of a real unlabeled ingestion source. |
| Fixed literal default date window (not `datetime.now()`) for event generation | Recorded here only — required for seeded-output determinism, same principle as Milestone 2 |
| Anomaly type selection weighted by event_type (device-acting types boosted for `new_device`; `device_changed` excluded from `new_device`) | Recorded here only — correctness fix agreed with user during Milestone 3 |

Full ADR-002 ("Airflow as the Orchestration Layer" — Airflow vs. alternatives broadly)
remains pending; do not cite it as written yet.

---

## Known Issues
- None blocking.

## Technical Debt
1. No pre-commit hook — formatting caught only at `pytest`/CI time. Flagged during
   Milestone 1, not yet addressed. Low priority.
2. CI does not validate the Airflow Docker Compose stack (deliberate scope decision,
   revisit once a real DAG exists).
3. The Airflow smoke-test DAG (`00_environment_smoke_test.py`) is temporary
   scaffolding; must be removed when Milestone 12 introduces the real orchestration DAG.
4. **New**: Anomaly injection is single-event-level only — no multi-event "bursts"
   (e.g. a cluster of `failed_login` events in a short window). Documented as a
   deliberate Milestone 3 scope decision, not a defect; burst/sequence-level anomalies
   are a reasonable future enhancement once temporal/velocity features exist to detect
   them (Milestone 6+).
5. **New**: `device_changed`, `password_changed`, `profile_changed`,
   `beneficiary_added` event types can still receive `geo_deviation`/
   `channel_deviation`/`amount_spike` anomalies (where eligible) with no special
   handling — only the `new_device` anomaly type has event-type-aware logic. Not
   addressed further in Milestone 3; acceptable for current scope.
6. **New**: The path from local CSV output to Databricks Delta ingestion is
   undesigned (see 📐 Designed Only above). Must be resolved before Bronze-layer
   work begins.

---

## Environment / Setup Information

(Unchanged since Milestone 1 — see prior verified values.)

| Item | Value | Verification status |
|---|---|---|
| OS | Windows (native, no WSL2 terminal use) | Stated by user |
| System Python | 3.14.2 | Stated by user (not the project's interpreter) |
| Project Python (via `uv`) | 3.11.16 | ✅ Verified via pytest platform output |
| `uv` version | 0.12.5 | Stated by user |
| Docker Desktop | Running, Linux containers via WSL2 backend | 🟡 Inferred |
| Git | Initialized, `main` branch, GitHub remote connected | ✅ Verified |
| Git version | 2.55.0.windows.4 | ✅ Verified |

## Repository Structure (as of Milestone 3)
```text
customer-event-detection/
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── .gitattributes
├── docs/
│ ├── project-status.md
│ ├── current-context.md
│ ├── architecture/ (empty)
│ ├── adr/
│ │ └── ADR-009-airflow-local-dev-topology.md
│ ├── security/ (empty)
│ ├── governance/ (empty)
│ ├── mlops/ (empty)
│ └── nfr/ (empty)
├── data_generation/
│ ├── customer_generator.py
│ └── event_generator.py
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
│ └── test_event_generator.py
├── docker/ (empty)
├── notebooks/ (empty)
└── .github/
└── workflows/
└── ci.yml
```

## Installed Dependencies (dev group only — no production dependencies yet)
- `pytest>=8.3.0`
- `ruff>=0.6.0`

## Airflow Status
- Version: 3.3.1, `LocalExecutor`, Postgres 16 backend
- DAGs present: 1 (`00_environment_smoke_test` — temporary, no pipeline logic)
- Not yet used to orchestrate the customer/event generators (still standalone scripts;
  orchestration integration is future work, see 📐 above)

## Testing Setup
- Framework: `pytest`
- Location: `tests/`
- Current coverage: environment smoke checks (2), customer generator (7), event
  generator (19) — **28 total**

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .` — both clean

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- Not yet re-confirmed green on `main` after Milestone 3 changes — **push and confirm
  before considering Milestone 3 fully closed for CI purposes**
- Does not yet build/run Docker or Airflow (by design, deferred)

## Commands Used to Verify Milestone 3
```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -v
uv run python data_generation/customer_generator.py --num-customers 1000 --seed 42
uv run python data_generation/event_generator.py --seed 42
```

Observed output:
```
28 passed in 1.46s
Generated 27128 events for 1000 customers -> data\raw\events.csv
Injected 542 anomalies (2.00%) -> data\raw\events_ground_truth.csv
```

---

## Next Recommended Task
**Milestone 4: Bronze-layer ingestion (Databricks/PySpark)** — land the synthetic
`customers.csv`/`events.csv` into Databricks as raw Delta tables. Requires first
resolving the undesigned local→Databricks handoff path (see 📐 Designed Only).
Not started — do not begin without explicit confirmation.