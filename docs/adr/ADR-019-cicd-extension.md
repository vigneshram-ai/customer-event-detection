# ADR-019: CI/CD Extension — DAG Integrity Testing and Live-Environment Smoke Test

**Status:** Proposed (pending live verification — see Milestone 14 in
`docs/project-status.md`)
**Date:** Milestone 14

## Context

Through Milestone 13, CI (`ci.yml`) consisted of a single job: lint →
format check → test, running 34 tests. This never touched Databricks,
Airflow, or any live environment. Two real gaps existed as a result:

1. **The Airflow DAGs (`ced_inference_pipeline`, `ced_training_pipeline`)
   were never validated by CI.** A broken import, a typo in an operator
   argument, or an accidentally-dropped task dependency would only be
   caught by manually running `airflow dags list` in WSL2 — if at all.
2. **`test_sp`, the service principal created and RBAC-scoped in
   Milestone 13, was verified once by hand and then sat unused.** Its
   credentials, and the grants attached to it, could silently drift or
   expire with nothing to notice.

## Problem

Extend CI/CD meaningfully, without pretending this project has
infrastructure it doesn't have. There is no deployed service for GitHub
Actions to push code to: the pipeline runs as manually/Airflow-triggered
Databricks notebooks, and Airflow itself runs on a non-persistent WSL2
instance (ADR-018). Classical "CD" (merge → auto-deploy → auto-run in
production) has no real target here, and building one would mean adding
infrastructure (a persistent scheduler, a deployment target) purely to
satisfy the word "CD" — the exact anti-pattern the project's operating
rules forbid (technology without genuine architectural purpose).

## Options Considered

**A — DAG integrity testing only.** Parse both DAGs with Airflow's
`DagBag` in a dedicated CI job (Airflow installed only there, never added
to `pyproject.toml` — consistent with ADR-018's treatment of Airflow as
WSL2-venv-only tooling). Catches import errors and structural regressions
before merge. Zero external dependency, zero secrets.

**B — Live smoke test using the personal PAT.** Simple, reuses the
existing credential. Rejected: a PAT is a long-lived, broadly-scoped
credential; placing it in GitHub Actions widens its blast radius for no
architectural benefit when a narrower option (C) already exists and sat
unused since Milestone 13.

**C — Live smoke test using `test_sp` OAuth client credentials.** Narrow,
already-scoped-to-least-privilege (`USE CATALOG` on `ced`; `USE SCHEMA` +
`SELECT` on `ced.training` only), and gives the Milestone 13 service
principal an actual job instead of remaining unused infrastructure.

**D — Full deploy automation** (auto-push notebook changes to the
workspace, auto-trigger DAG runs on merge). Rejected: no persistent
scheduler exists to receive a triggered run in a meaningful way (ADR-018),
and the project's own rules explicitly keep both DAGs `schedule=None` by
design. Building auto-deploy against that would be automation theater.

**E — Docker-based CI stage.** Rejected: nothing in the current
architecture runs in a container. Docker exists in the repo structure as
a placeholder for a future milestone, not as something with a genuine
purpose to exercise in CI today.

## Decision

Implement **A + C**:

- New `dag-integrity` CI job: installs `apache-airflow==3.3.1` +
  `apache-airflow-providers-databricks==7.18.1` (pinned to the real
  WSL2 versions) into an isolated, throwaway environment; runs
  `airflow/tests/test_dag_integrity.py`, which asserts zero `DagBag`
  import errors, the expected DAG IDs, the expected task lists in order,
  that both DAGs remain unscheduled (`NullTimetable`, i.e. `schedule=None`
  — a deliberate ADR-018 property, not an oversight, and this test exists
  so re-enabling a schedule is a reviewed decision), and that retries are
  configured.
- New `databricks-smoke-test` CI job: authenticates as `test_sp` via
  OAuth M2M (env vars `DATABRICKS_HOST` / `DATABRICKS_CLIENT_ID` /
  `DATABRICKS_CLIENT_SECRET`, sourced from GitHub Actions secrets
  `DATABRICKS_HOST` / `DATABRICKS_SP_CLIENT_ID` /
  `DATABRICKS_SP_CLIENT_SECRET`), then performs two **read-only** checks:
  reading catalog `ced` and reading schema `ced.training` — exactly the
  grant chain manually verified in Milestone 13. **Restricted to `push`
  events on `main` only, never `pull_request`** — a public repo can
  receive PRs from anyone, and a PR-triggered workflow must not have
  access to live-workspace secrets. This is a trust-boundary decision,
  not incidental workflow config.

Rejected B, D, and E for the reasons above.

## Rationale

- Both additions extend *testing depth*, not deployment scope — consistent
  with the project's batch-only, manually-triggered architecture.
- The smoke test automates a check that was previously only ever run by
  hand (Milestone 13's own verification commands), which is a genuine
  improvement in detection speed for credential/grant drift — not a new
  capability invented for its own sake.
- Keeping Airflow out of `pyproject.toml` (installed only inside the CI
  job's own throwaway environment) preserves the existing, deliberate
  separation between project dependencies and operator/orchestration
  tooling (same pattern as the Databricks CLI, ADR-018).
- `airflow/tests/` is kept outside `tests/` (pytest's configured
  `testpaths`) specifically so the main `lint-and-test` job's environment
  — which has no Airflow installed — never attempts to collect it.

## Consequences

- Three CI jobs instead of one; `dag-integrity` adds Airflow's install
  time (~1–2 minutes) to every push/PR. `databricks-smoke-test` only runs
  on `main`, so PR feedback time is unaffected.
- Three new GitHub Actions secrets to manage: `DATABRICKS_HOST`,
  `DATABRICKS_SP_CLIENT_ID`, `DATABRICKS_SP_CLIENT_SECRET`.
- `test_sp` now has a genuine, narrow, automated consumer — resolves the
  Milestone 13 "created but unused" gap (though migrating the *training
  pipeline itself* to run as `test_sp` remains separate, undone future
  work — this ADR does not claim that).
- If `test_sp`'s credentials or grants are ever rotated/revoked without
  updating the GitHub secret, `main`'s CI will correctly go red — this is
  the intended failure mode, not a bug (verified as part of Milestone 14's
  test plan via a deliberate negative test).

## Future Considerations

- Migrate `train_model.py` / `validate_and_promote_model.py` to actually
  run as `test_sp` (or a renamed, formally-adopted equivalent) — still
  open per ADR-007.
- If a persistent orchestration target ever exists (e.g., a
  continuously-running Airflow instance, or Databricks Workflows as an
  alternative), revisit whether genuine CD (auto-trigger on merge) becomes
  architecturally justified — it is not today.
- Expand the smoke test's coverage (e.g., confirm the `champion` alias
  still resolves in the model registry) if a concrete need for that
  signal emerges.