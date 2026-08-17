# Project Status — Customer Event Detection ML Solution

_Last updated: End of Milestone 2_

_Milestone 1 status: IMPLEMENTED AND VERIFIED (with noted exceptions below)_
_Milestone 2 status: IMPLEMENTED AND VERIFIED — customer entity only (event generation is Milestone 3)_

## Status Legend
- ✅ IMPLEMENTED & VERIFIED — built, run, and confirmed working by the user with observed output
- 🟡 IMPLEMENTED, NOT FULLY VERIFIED — built and appears to work, but not confirmed with explicit command output
- 📐 DESIGNED ONLY — documented/decided, not built
- ⏳ FUTURE — planned, not started

---

## Completed Work

### ✅ Implemented & Verified — Milestone 1
- Repository skeleton created matching the approved structure (`docs/`, `data_generation/`,
  `data_quality/`, `feature_engineering/`, `training/`, `inference/`, `monitoring/`,
  `airflow/dags/`, `tests/`, `docker/`, `notebooks/`, `.github/workflows/`).
- Git initialized on `main`, `.gitignore` and `.gitattributes` in place (LF enforcement
  for Windows/Linux-container interop).
- `pyproject.toml` — `uv`-managed, Python pinned to 3.11 via `uv python pin`, dependencies
  declared under `[dependency-groups] dev` (PEP 735).
- `ruff` configured for both linting and formatting (single tool, `[tool.ruff]` in
  `pyproject.toml`). `uv run ruff check .` and `uv run ruff format --check .` both pass.
- `pytest` configured (`[tool.pytest.ini_options]`), smoke test suite
  (`tests/test_environment.py`, 2 tests) passing via `uv run pytest -v`.
- Airflow 3.3.1 running locally via Docker Compose, `LocalExecutor` (Redis/worker/flower
  removed). `docker ps` confirmed exactly 5 healthy containers.
- Airflow web UI reachable at `localhost:8080`, login confirmed. Smoke-test DAG
  (`00_environment_smoke_test`) triggered manually and completed successfully.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) present on `main`, green.
- `README.md` created with accurate, minimal, non-aspirational content.
- Docker Desktop functioning correctly.

### ✅ Implemented & Verified — Milestone 2 (Synthetic Customer Generator)
- `data_generation/customer_generator.py` — deterministic, seeded synthetic customer
  generator. Stdlib only (`random`, `csv`, `dataclasses`, `argparse`) — no pandas/Spark
  introduced, since there is no data-processing need yet to justify them.
- `Customer` entity: `customer_id`, `account_age_days`, `home_country`, `normal_channel`,
  `normal_device`.
- Weighted, non-uniform distributions chosen to support future anomaly-detection
  features (not arbitrary): NL-dominant home country with EU long tail, mobile-dominant
  channel mix, tiered account age (new/established/veteran).
- CLI entry point (`--num-customers`, `--seed`, `--output`) writing to CSV.
- `tests/test_customer_generator.py` — 7 tests: requested count, determinism under same
  seed, divergence under different seeds, ID uniqueness, input validation, distribution
  sanity check, CSV round-trip.
- `pyproject.toml` updated: `pythonpath = ["."]` added to `[tool.pytest.ini_options]` —
  required once tests began importing project packages (`data_generation`) directly;
  first exposed in this milestone, fixes the issue for all future milestones' tests too.
- `.gitignore` updated: `data/` excluded (fully reproducible via `--seed`, so nothing
  generated is committed); `data/raw/.gitkeep` preserves the folder path in Git.
- **Command-line verification performed by user, with observed output:**
  - `uv run ruff check .` → pass
  - `uv run ruff format --check .` → pass (after one auto-fix round; same category of
    issue as Milestone 1 — missing blank line after docstring / missing trailing
    newline, genuine tool behavior, not flakiness)
  - `uv run pytest -v` → **9/9 passed** (7 new + 2 existing from Milestone 1)
  - `uv run python -m data_generation.customer_generator --num-customers 1000 --seed 42`
    → generated `data/raw/customers.csv`; confirmed 1001 lines (1 header + 1000 rows);
    header and sample rows inspected and correct
  - End-to-end CLI determinism confirmed: regenerated to a second file
    (`customers_check.csv`) with the same seed; `Compare-Object` against the original
    reported no differences

### 🟡 Implemented, Not Fully Verified
- None

### 📐 Designed Only
- Full "Airflow vs. alternatives" rationale (broader ADR-002) — not yet formally
  argued. Adopted Airflow per approved project scope; only compared *within* Airflow
  (version, executor) — see ADR-009.

### ⏳ Future
- Event generation (Milestone 3) — explicitly deferred; customers are reference/dimension
  data that events will consume as input, so it made sense to build and verify them in
  isolation first.
- Everything from Milestone 3 onward per the approved roadmap.

---

## Current Work
None in progress. Milestone 2 is closed.

## Pending Work
Milestones 3–23 per the approved roadmap, starting with synthetic event generation
(referencing the customer population built in Milestone 2).

---

## Architecture Decisions Made

| Decision | Where documented |
|---|---|
| Airflow 3.3.1 (not 2.x), `LocalExecutor` (not Celery) for local development | **ADR-009** |
| `uv` over Poetry/pip | Recorded here only — tooling preference, not ADR-worthy |
| `ruff` for lint + format (single tool) | Recorded here only — same reasoning |
| No Makefile; direct `uv`/`docker compose` commands | Recorded here only — reversible, no architectural weight |
| Stdlib-only synthetic customer generator (no pandas at this stage) | Recorded here only — no data-processing need yet; pandas/Spark reserved for genuine volume/transformation work starting Milestone 3+ |
| `pythonpath = ["."]` added to pytest config | Recorded here only — packaging-mechanics fix, not an architectural trade-off; enables cross-package test imports project-wide |
| `data/` gitignored, regenerated on demand via seeded CLI | Recorded here only — reproducibility via `--seed` makes committing generated data redundant |

Full ADR-002 ("Airflow as the Orchestration Layer" — Airflow vs. alternatives broadly)
remains pending; do not cite it as written yet.

---

## Known Issues
- None blocking. Both CI failures encountered during Milestone 1 setup were resolved
  (missing trailing newlines caught by `ruff format --check`) and are understood as
  expected tool behavior, not recurring issues.
- The `ModuleNotFoundError` encountered early in Milestone 2 (pytest couldn't resolve
  `data_generation` as an importable package) was a project-configuration gap, not a
  code defect. Resolved via `pythonpath = ["."]`; not a recurring issue going forward.

## Technical Debt
1. No pre-commit hook — formatting issues are currently caught only at `pytest`/CI time,
   not before commit. Flagged during Milestone 1, not yet addressed. Low priority.
2. CI does not validate the Airflow Docker Compose stack (deliberate scope decision for
   Milestone 1). Revisit once a real DAG exists.
3. The Airflow smoke-test DAG (`00_environment_smoke_test.py`) is temporary scaffolding;
   must be removed when Milestone 12 introduces the real orchestration DAG.
4. `customer_generator.py` CLI has no upper-bound validation on `--num-customers` and no
   path-safety checks on `--output`. Low priority — revisit only if it becomes a real
   usability issue at larger scales.

---

## Environment / Setup Information

| Item | Value | Verification status |
|---|---|---|
| OS | Windows (native, no WSL2 terminal use) | Stated by user |
| System Python | 3.14.2 | Stated by user (not the project's interpreter) |
| Project Python (via `uv`) | 3.11, pinned via `.python-version` | ✅ Verified (`uv run python --version`; also confirmed via pytest header: CPython 3.11.16) |
| `uv` version | 0.12.5 | Stated by user |
| Docker Desktop | Running, Linux containers via WSL2 backend | 🟡 Inferred from healthy containers, not directly captured |
| Docker Compose | v2 syntax (`docker compose`, not `docker-compose`) | ✅ Functionally verified |
| Git | Initialized, `main` branch, GitHub remote connected | ✅ Verified |
| Git version | 2.55.0.windows.4 | ✅ Verified |

## Repository Structure (as of Milestone 2)
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
│ ├── __init__.py
│ └── customer_generator.py
├── data/ (gitignored — regenerated via CLI)
│ └── raw/
│   └── .gitkeep
├── data_quality/ (empty)
├── feature_engineering/ (empty)
├── training/ (empty)
├── inference/ (empty)
├── monitoring/ (empty)
├── airflow/
│ ├── docker-compose.yaml
│ ├── .env
│ ├── dags/
│ │ └── 00_environment_smoke_test.py
│ └── logs/
├── tests/
│ ├── test_environment.py
│ └── test_customer_generator.py
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
- Services deliberately removed: redis, worker, flower
- DAGs present: 1 (`00_environment_smoke_test` — temporary, no pipeline logic)
- No change in Milestone 2 — Airflow is not yet orchestrating data generation.

## Testing Setup
- Framework: `pytest`
- Location: `tests/`
- Current coverage: environment/harness smoke checks (2 tests) + synthetic customer
  generator (7 tests) — 9 tests total, all passing
- Config note: `pythonpath = ["."]` added in Milestone 2 to enable importing project
  packages directly from `tests/`

## Linting/Formatting Setup
- Tool: `ruff` (single tool for both)
- Config: `[tool.ruff]` in `pyproject.toml`
- Verified commands: `uv run ruff check .`, `uv run ruff format --check .`

## CI/CD Status
- GitHub Actions workflow `ci.yml`: lint → format check → test, on push/PR to `main`
- Confirmed green after fixing two real formatting failures (Milestone 1)
- Milestone 2 changes not yet pushed/verified against CI — see Next Recommended Task
- Does not yet build/run Docker or Airflow (by design, deferred)

## Commands Used to Verify Milestone 2
```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -v
uv run python -m data_generation.customer_generator --num-customers 1000 --seed 42
Get-Content data\raw\customers.csv -TotalCount 5
(Get-Content data\raw\customers.csv | Measure-Object -Line).Lines
uv run python -m data_generation.customer_generator --num-customers 1000 --seed 42 --output data/raw/customers_check.csv
Compare-Object (Get-Content data\raw\customers.csv) (Get-Content data\raw\customers_check.csv)
```

---

## Next Recommended Task
**Milestone 3: Synthetic event generator** — configurable, seeded, reproducible
banking events referencing the Milestone 2 customer population, including deliberate
normal-vs-anomalous behaviour injection. Not started.

Before starting Milestone 3, recommend: commit and push Milestone 2 changes, confirm CI
is green on the new test/module additions.
