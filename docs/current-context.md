# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestone 1 (Repository & Local Development Environment) is **complete and verified**.
Milestone 2 has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch), CI is green.
- Local Airflow (Docker Compose, `LocalExecutor`) is running and has successfully executed
  one manual smoke-test DAG. It has no real pipeline logic yet.
- No application code exists yet — no data generator, no Spark, no MLflow, no models.
  Every reference to those in earlier planning docs is 📐 DESIGNED ONLY / ⏳ FUTURE, not built.
- `pyproject.toml` has zero production dependencies. Only `pytest` and `ruff` (dev group).

## Environment Snapshot
- Windows (native, no WSL2 terminal)
- `uv` 0.12.5, project Python 3.11 (system Python is 3.14.2 — irrelevant to the project,
  `uv` manages its own interpreter)
- Docker Desktop running, Airflow 3.3.1 via Docker Compose, LocalExecutor
- Git remote connected, CI passing on GitHub Actions
- Git version is 2.55.0.windows.4
- Docker version
    Client:
        Version:           29.7.2
        API version:       1.55
        Go version:        go1.26.5
        Git commit:        a7dcaa6
        Built:             Wed Aug  5 18:31:33 2026
        OS/Arch:           windows/amd64
        Context:           desktop-linux
    Server: Docker Desktop 4.86.0 (236216)
        Engine:
        Version:          29.7.2
        API version:      1.55 (minimum version 1.40)
        Go version:       go1.26.5
        Git commit:       6a43e3d
        Built:            Wed Aug  5 18:28:36 2026
        OS/Arch:          linux/amd64
        Experimental:     false
        containerd:
        Version:          v2.2.5
        GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
        runc:
        Version:          1.3.6
        GitCommit:        v1.3.6-0-g491b69ba
        docker-init:
        Version:          0.19.0
        GitCommit:        de40ad0
- Docker Compose version v5.3.1

## Known Gaps (do not silently "fix" these — ask the user first)
- Full ADR-002 (Airflow vs. non-Airflow alternatives) not yet written — only the
  narrower executor/version decision is documented (ADR-009).

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and verified with
  observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Every technology must have a stated architectural purpose — no CV-padding.

## Immediate Next Step
Start Milestone 2: **Synthetic customer generator** — explain → design → implement →
test → verify → document → interview implications, in that order, small increment first
(customer entity only — event generation is Milestone 3).

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-009-airflow-local-dev-topology.md` — Airflow version/executor decision
- `README.md` — public-facing summary (kept minimal, accurate)