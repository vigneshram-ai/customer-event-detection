# ADR-002: Airflow as the Orchestration Layer

**Status:** Accepted (retroactively formalized at Milestone 12; Airflow was
selected and stood up in Milestone 1, but this ADR was left unwritten until
real orchestration existed to reason about)

## Context

The CED pipeline consists of distinct, dependent stages: Bronze ingestion,
Silver validation/transformation, Gold feature engineering, model
training/validation/promotion, batch inference, and monitoring. Through
Milestone 11, all of these ran as independently-executed Databricks notebooks
via manual "Run All" — functionally correct, but with no dependency
enforcement, no automatic retry on transient failure, no scheduling, and no
single place to observe whether the end-to-end pipeline succeeded.

## Problem

How should multi-stage, dependent data/ML pipeline execution be coordinated,
and is a dedicated orchestrator justified for a project at this scale?

## Options Considered

1. **No orchestrator — keep manual "Run All" per notebook.**
   Simplest possible option. Rejected: no dependency enforcement (nothing
   stops Gold running against stale Silver output), no retry semantics, no
   audit trail of pipeline-level success/failure, and doesn't demonstrate
   orchestration competency — a real gap for a Solution Architect portfolio
   given orchestration is a named requirement in the target role.

2. **Databricks Workflows (native Databricks job orchestration).**
   Would avoid the cross-platform complexity this milestone hit (WSL2, the
   serverless compute compatibility issue). Rejected as the primary
   orchestrator for this project specifically because the target resume
   statement and role require demonstrated Airflow experience, not just
   "a" orchestrator — the architectural reasoning being demonstrated is
   Airflow-specific (DAGs, operators, retries, scheduling as first-class
   concepts), not just "get the pipeline to run in order."

3. **Apache Airflow.**
   Selected. Industry-standard orchestrator, directly matches the target
   resume statement, and forces genuine engagement with orchestration
   concepts (task dependencies, retries, idempotency, scheduling) as
   distinct from the computation happening inside each task.

## Decision

Use Apache Airflow as the orchestration layer, with Databricks/PySpark
notebooks as the actual computation, invoked from Airflow via the
`apache-airflow-providers-databricks` provider. Airflow owns *when* and *in
what order* stages run and how failures are handled; it does not perform any
data processing itself — that discipline (orchestration vs. computation) is
treated as a first-class architectural principle, not just a tooling choice.

## Rationale

- Directly demonstrates the orchestration competency named in the target
  role, using the same tool named in the target resume statement.
- Keeps computation and orchestration cleanly separated: Databricks
  notebooks remain independently runnable and testable (as they have been
  since Milestone 4), while Airflow adds dependency ordering, retries, and
  a single pane of glass for pipeline-level success/failure — without
  requiring any changes to notebook logic itself.
- Matches how this pattern is actually used in production data platforms:
  Airflow (or an equivalent orchestrator) coordinating jobs on a separate
  compute platform (Databricks, Spark, etc.) is a standard, defensible
  architecture, not a contrived pairing.

## Consequences

- **Two runtime environments to maintain**: the Databricks workspace
  (compute) and a separate Airflow instance (orchestration). This is a
  real, accepted operational cost, not eliminated by this decision.
- **Local execution constraint discovered at Milestone 12**: Airflow does
  not support native Windows Python installation. Combined with this
  laptop's inability to run the originally-planned Docker Compose stack
  (resource constraints), this forced an environment change — Airflow now
  runs natively inside WSL2 Ubuntu (not Docker), reversing the
  "Windows native, no WSL2 terminal use" principle stated since Milestone 1.
  Documented honestly as an environment correction, not silently patched
  around — see ADR-018 and the Milestone 12 `current-context.md` update.
- **Databricks Free Edition serverless compute compatibility required
  empirical discovery**, not something documented clearly by Databricks/
  Airflow's own docs at the time of this project — see ADR-018 for the
  specific technical finding (`DatabricksSubmitRunOperator` with the
  multi-task `tasks=[...]` shape, no cluster spec).
- **This Airflow instance only runs while manually started** (`airflow
  standalone` in a WSL2 shell) — there is no persistent scheduler process
  surviving a laptop restart or shutdown. This is an accepted, explicit
  constraint of the local-first, zero-cost architecture: both
  `ced_inference_pipeline` and `ced_training_pipeline` are configured with
  `schedule=None` (manually triggered) for this reason, not as a
  temporary state — a real cron-based schedule would silently never fire
  on this setup. Documented as a known limitation, with the production
  equivalent (Airflow via Composer/MWAA/Astronomer, always-on) noted as
  the Azure/production evolution path.

## Future Considerations

- A managed/always-on Airflow deployment (Cloud Composer, MWAA, Astronomer)
  would remove the "must be manually started" constraint — out of scope
  for this project's zero-cost architecture, documented as a production
  evolution path only.
- Databricks Workflows remains a reasonable alternative orchestrator for a
  Databricks-only shop; retained here as a documented alternative, not
  implemented, since it wouldn't demonstrate the specifically-required
  Airflow competency.