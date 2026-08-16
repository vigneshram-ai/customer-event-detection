# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 1_

_Milestone 1 status: IMPLEMENTED AND VERIFIED (with noted exceptions below)_

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified
- Repository skeleton created matching the approved structure (`docs/`, `data_generation/`,
  `data_quality/`, `feature_engineering/`, `training/`, `inference/`, `monitoring/`,
  `airflow/dags/`, `tests/`, `docker/`, `notebooks/`, `.github/workflows/`).
- Git initialized on `main`, `.gitignore` and `.gitattributes` in place (LF enforcement
  for Windows/Linux-container interop).
- `pyproject.toml` — `uv`-managed, Python pinned to 3.11 via `uv python pin`, dependencies
  declared under `[dependency-groups] dev` (PEP 735 — corrected from the initially-used
  deprecated `[tool.uv.dev-dependencies]` after a CI warning surfaced it).
- `ruff` configured for both linting and formatting (single tool, `[tool.ruff]` in
  `pyproject.toml`). `uv run ruff check .` and `uv run ruff format --check .` both pass.
- `pytest` configured (`[tool.pytest.ini_options]`), smoke test suite
  (`tests/test_environment.py`, 2 tests) passing via `uv run pytest -v`.
- Airflow 3.3.1 running locally via Docker Compose, `LocalExecutor` (trimmed from the
  official CeleryExecutor quick-start — Redis, `airflow-worker`, and `flower` removed).
- `docker ps` confirmed exactly 5 healthy containers: `postgres`, `airflow-scheduler`,
  `airflow-dag-processor`, `airflow-api-server`, `airflow-triggerer`. No Redis/worker present.
- Airflow web UI reachable at `localhost:8080`, login confirmed (`airflow`/`airflow`).
- Smoke-test DAG (`00_environment_smoke_test`) triggered manually and completed successfully
  (green) in the UI.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) present on `main`, triggers on
  push/PR, and has produced a **green run** after two real, user-encountered failures
  (both `ruff format` catching missing trailing newlines — genuine tool behavior, not
  flakiness).
- `README.md` created with accurate, minimal, non-aspirational content.
- Docker Desktop functioning correctly

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (the broader ADR-002 scoped in the original
  roadmap — Airflow vs. cron/Dagster/Prefect/plain scripts) has **not** been formally
  argued yet. We adopted Airflow per the approved project scope, but only compared
  *within* Airflow (version, executor) — see ADR-009 below.

### ⏳ Future
- Everything from Milestone 2 onward (see roadmap).

---

## Current Work
None in progress. Milestone 1 is closed.

## Pending Work
Milestones 2–23 per the approved roadmap, starting with the synthetic customer generator.

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor` (not Celery) for local development | **ADR-009** (new — see below) |
| `uv` over Poetry/pip | Recorded here only — judged not ADR-worthy (tooling preference, not a system architecture trade-off with production consequences) |
| `ruff` for lint + format (single tool) | Recorded here only — same reasoning |
| No Makefile; direct `uv`/`docker compose` commands | Recorded here only — environment convenience, reversible, no architectural weight |

Full ADR-002 ("Airflow as the Orchestration Layer" — Airflow vs. alternatives broadly)
remains pending; do not cite it as written yet.

---

## Known Issues
- None blocking. Both CI failures encountered during setup were resolved (missing
  trailing newlines caught by `ruff format --check`) and are not recurring issues —
  they're now understood as expected tool behavior.

## Technical Debt
1. No pre-commit hook — formatting issues are currently caught only at `pytest`/CI time,
   not before commit. Flagged during Milestone 1, not yet addressed. Low priority, cheap
   to add later.
2. CI does not validate the Airflow Docker Compose stack (deliberate scope decision for
   Milestone 1 — no pipeline logic exists yet to justify the added CI cost/complexity).
   Revisit once a real DAG exists.
3. The Airflow smoke-test DAG (`00_environment_smoke_test.py`) is temporary scaffolding;
   must be removed when Milestone 12 introduces the real orchestration DAG.

---

## Environment / Setup Information

| Item | Value | Verification status |
|---|---|---|
| OS | Windows (native, no WSL2 terminal use) | Stated by user |
| System Python | 3.14.2 | Stated by user (not the project's interpreter) |
| Project Python (via `uv`) | 3.11, pinned via `.python-version` | ✅ Verified (`uv run python --version`) |
| `uv` version | 0.12.5 | Stated by user |
| Docker Desktop | Running, Linux containers via WSL2 backend | 🟡 Inferred from healthy containers, not directly captured |
| Docker Compose | v2 syntax (`docker compose`, not `docker-compose`) | ✅ Functionally verified (commands ran successfully) |
| Git | Initialized, `main` branch, GitHub remote connected | ✅ Verified (`git status`, `git branch --show-current`, successful push) |
| Git version | 2.55.0.windows.4 | ✅ Verified |

## Repository Structure (as of Milestone 1)
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
├── data_generation/ (empty)
├── data_quality/ (empty)
├── feature_engineering/ (empty)
├── training/ (empty)
├── inference/ (empty)
├── monitoring/ (empty)
├── airflow/
│ ├── docker-compose.yaml (trimmed from official Airflow 3.3.1 quick-start)
│ ├── .env
│ ├── dags/
│ │ └── 00_environment_smoke_test.py
│ └── logs/
├── tests/
│ └── test_environment.py
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
- Version: 3.3.1
- Executor: `LocalExecutor`
- Backend DB: Postgres 16
- Services running: scheduler, dag-processor, api-server, triggerer, postgres
- Services deliberately removed: redis, worker, flower (CeleryExecutor-only, unneeded locally)
- DAGs present: 1 (`00_environment_smoke_test` — temporary, no pipeline logic)

## Testing Setup
- Framework: `pytest`
- Location: `tests/`
- Current coverage: environment/harness smoke checks only (2 tests) — no application
  code exists yet to test

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- Config: `[tool.ruff]` in `pyproject.toml`
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .`

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- Confirmed green after fixing two real formatting failures
- Does not yet build/run Docker or Airflow (by design, deferred)

## Commands Used to Verify the Environment (this milestone)
```powershell
uv run python --version
uv run pytest --version
uv run ruff --version
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
docker ps
git status
git branch --show-current
git log --oneline -5
```

---

## Next Recommended Task
**Milestone 2: Synthetic customer generator** — configurable, seeded, reproducible
customer profiles with unit tests. Not started.