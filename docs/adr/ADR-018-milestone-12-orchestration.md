# ADR-018: Milestone 12 — Real Orchestration (Two-DAG Split, Serverless Compute Compatibility, WSL2 Environment Change)

**Status:** Accepted and Implemented

## Context

Milestone 12 replaced the temporary smoke-test DAG with real orchestration
of the CED pipeline's Databricks notebooks (Bronze, Silver, Gold, training,
validation/promotion, batch inference, monitoring), which had previously
only run via manual "Run All" in the Databricks UI.

## Problem

Three distinct design questions had to be resolved before implementation:
(1) whether training belongs in the same DAG as inference, (2) whether the
existing Docker Compose Airflow environment (Milestone 1) could actually run
on this laptop, and (3) how to invoke a Databricks notebook from Airflow
against Free Edition, which provides serverless compute only (no clusters).

## Decision 1 — Two-DAG Split (Inference vs. Training)

**Decision:** `ced_inference_pipeline` (Bronze → Silver → Gold → batch
inference → monitoring) and `ced_training_pipeline` (train_model →
validate_and_promote_model) are separate, independently-triggered DAGs, not
chained to one another.

**Rationale:** Retraining is a deliberate, reviewed event in real MLOps
practice (new data, scheduled cadence, or a monitoring-triggered signal),
not something that should fire on every inference run. Chaining training
into the inference path would retrain the model on every run against the
same static synthetic dataset, producing no new information while
polluting the model registry with near-identical versions and adding
runtime with no benefit.

**Connection mechanism:** The two DAGs are decoupled through the Unity
Catalog model registry, not through Airflow dependencies —
`ced_training_pipeline` updates which model version holds the `champion`
alias; `ced_inference_pipeline` always reads whichever version currently
holds it, with no direct awareness of when or whether training last ran.
This is an intentional architectural point, consistent with how production
MLOps systems typically decouple training and serving cadences.

**Consequence:** `ced_training_pipeline` assumes `ced.gold.customer_events_features`
is already current; it does not re-run Bronze/Silver/Gold itself. Training
against a deliberately-available data snapshot (rather than implicitly
depending on `ced_inference_pipeline`'s own schedule) was chosen over an
implicit cross-DAG dependency, judged more architecturally honest for a
portfolio project.

**Baseline detector excluded entirely.** `baseline_detector.py` (Milestone 7)
was a one-time analytical comparison used to justify choosing an ML approach
over a rules-based one — it is not part of the production inference path
(the champion model is) and was deliberately left out of both DAGs.

## Decision 2 — WSL2 Native, Not Docker Compose

**Context:** The Milestone 1 Airflow environment (Docker Compose,
`LocalExecutor`) could not run on this laptop at Milestone 12 — Docker
Desktop's own overhead made the machine unusable before Airflow's containers
were even healthy, independent of Airflow itself.

**Options considered:**
1. Trim the Docker Compose stack (disable optional containers, cap memory) —
   untested whether this would be sufficient given Docker Desktop itself
   was the bottleneck, not just Airflow's containers.
2. Downgrade to Airflow 2.x (fewer separate containers than 3.x's split
   apiserver/scheduler/dag-processor/triggerer architecture) — rejected,
   would reverse the Airflow 3.3.1 decision (ADR-009) without addressing
   the actual Docker Desktop overhead problem.
3. Run Airflow natively on Windows — **not viable at all**: Airflow does
   not support native Windows Python installation (a hard platform check
   in the package itself, not a configuration issue).
4. Run Airflow natively inside WSL2 Ubuntu (`airflow standalone`, SQLite,
   `SequentialExecutor`), no Docker at all. **Selected.**

**Decision:** Airflow 3.3.1 runs natively inside a dedicated WSL2 Ubuntu
distro (`Ubuntu`, separate from the minimal `docker-desktop` utility
distro), in a Python 3.12 virtual environment, using `airflow standalone`
(SQLite metadata DB, `SequentialExecutor`). The `dags_folder` in
`airflow.cfg` points at the Windows-mounted project path
(`/mnt/d/.../customer-event-detection/airflow/dags`), so DAG files remain
version-controlled in the same repository as the rest of the project — no
separate DAG-only repo or copy step.

**Consequence — documented environment correction:** This reverses the
"Windows native, no WSL2 terminal use" principle stated since Milestone 1.
Not silently patched around — recorded explicitly here and in the
Milestone 12 `current-context.md` update as a genuine environment change,
made necessary by a real resource constraint discovered at this milestone,
not a preference change.

**Consequence — no persistent scheduler.** Since `airflow standalone` only
runs while manually started in a WSL2 shell, there is no scheduler process
surviving laptop shutdown/restart. Both DAGs are configured `schedule=None`
(manual trigger only) as a direct consequence — see ADR-002.

**Rejected for this milestone:** trimming the Docker Compose stack (Option
1) was not attempted once the WSL2-native path proved to work cleanly and
directly addressed the actual bottleneck (Docker Desktop's own overhead),
rather than an unverified partial mitigation.

## Decision 3 — Serverless Compute Invocation

**Problem:** Databricks Free Edition provides serverless compute only — no
cluster IDs exist to reference. `DatabricksNotebookOperator`
(`apache-airflow-providers-databricks`) requires `existing_cluster_id`,
`job_cluster_key`, or `new_cluster`; none apply. Empirically confirmed
(not merely inferred from docs) that this operator briefly gained
serverless support upstream (PR #45188, Jan 2025) but it was reverted two
weeks later (PR #46724, Feb 2025) and is absent in the currently installed
provider version (7.18.1) — this operator cannot be used against Free
Edition at all.

**First attempt, confirmed failing:** `DatabricksSubmitRunOperator` using
the legacy single-task shorthand (`notebook_task=` as a top-level operator
argument) — failed with a `400 INVALID_PARAMETER_VALUE` from the
Databricks Jobs API: *"One of job_cluster_key, new_cluster, or
existing_cluster_id must be specified. For serverless compute, please use
multi-task with tasks array instead."* This confirmed Free Edition
serverless *is* reachable via an externally-submitted job (auth,
connectivity, and permissions all succeeded) — the request shape was
simply wrong.

**Working solution, empirically verified:** `DatabricksSubmitRunOperator`
using the multi-task `tasks=[...]` parameter — a list of task-spec dicts,
each with its own `task_key` and nested `notebook_task`, with no cluster
field anywhere in the request. Verified via a minimal single-task test DAG
(`99_databricks_serverless_test.py`, since deleted) against
`03.gold_feature_engineering`: job submitted, reached `RUNNING` state,
polled to completion, returned success. All five production tasks in
`ced_inference_pipeline` and both tasks in `ced_training_pipeline` use this
same pattern via a shared `make_notebook_task()` helper in each DAG file.

**Consequence:** This is now the only supported invocation pattern for
Databricks notebooks from this Airflow instance. Any future notebook added
to either DAG must use the same `tasks=[...]` shape — direct use of
`DatabricksNotebookOperator` or the legacy `notebook_task=` shorthand will
fail identically.

## Verified Results

- `ced_inference_pipeline` — full run, all five tasks succeeded. Verified
  (not just "ran without error"): fresh timestamps confirmed in
  `ced.bronze`, `ced.gold.customer_events_features`, and
  `ced.inference.detection_results`; `ced.monitoring.batch_quality_report`
  grew from 158 to 237 rows (exactly +79, matching one clean monitoring
  run with a new `run_id`, no double-write); Silver `_rejects` tables
  confirmed at 0, consistent with prior milestones.
- `ced_training_pipeline` — full run, both tasks succeeded. This is also
  the **first live execution of the champion/challenger comparison branch**
  (previously Technical Debt #20, unverified since Milestone 9): v2 trained,
  passed all three validation gate thresholds (`recall_channel_deviation`
  1.0, `recall` 1.0, `precision` 0.9879), tagged `challenger`; F1 comparison
  against champion v1 was an exact tie (0.9939 vs. 0.9939); the documented
  tie-break rule ("ties favor the incumbent champion," ADR-015) correctly
  held v1 as `champion` and tagged v2 `archived`. Confirms the
  champion/challenger logic behaves as designed under a real tie, not just
  that the code path executes. **Technical Debt #20 is resolved.**
- CI confirmed green (lint, format, tests) — no changes to
  `pyproject.toml`, no new local dependencies (the Databricks provider is
  installed only inside the Airflow WSL2 venv, not the project's `uv`
  environment).

## Future Considerations

- Monitoring's `run_id` generation uses a fresh UUID per run, not one
  derived deterministically from Airflow's own run context. This means an
  Airflow-level task retry after a partial failure could, in principle,
  double-write a monitoring batch under a new `run_id`. Not fixed at this
  milestone — both DAGs are manually triggered only, so the practical risk
  is low; revisit if/when either DAG moves to a real schedule.
- Technical Debt #24 (batch inference `overwrite`, no historical
  accumulation) remains open — not addressed by adding orchestration.
- A managed, always-on Airflow deployment removes the "must be manually
  started" constraint entirely — documented as the Azure/production
  evolution path (see project's Azure-mapping documentation), not
  implemented here.