# ADR-009: Airflow Version and Executor Choice for Local Development

## Status
Accepted (for local development environment only — production topology is a separate,
future decision, not implied by this ADR)

## Context
Milestone 1 required a working local Airflow environment. Airflow's official Docker
Compose quick-start (as of Airflow 3.3.1, the current stable release) ships 8 services
by default — scheduler, dag-processor, api-server, worker, triggerer, init, postgres,
and redis — built around `CeleryExecutor`, a distributed task queue designed for
multi-machine production deployments.

Airflow 3.x is architecturally distinct from 2.x: it introduces a Task Execution API
(AIP-72) that decouples task execution from direct metadata-database access, splitting
what used to be "scheduler + webserver" into scheduler, dag-processor, api-server, and
triggerer as independent services — a change that exists regardless of executor choice.

## Problem
1. Should this project target Airflow 2.x (simpler, older, still widely deployed in
   production today) or 3.x (current stable, architecturally different)?
2. Should local development use the default `CeleryExecutor` topology (Redis + worker),
   or a simpler single-machine alternative?

## Options Considered

**Airflow version:**
- **2.x (e.g., 2.10/2.11)** — simpler two-service split (webserver + scheduler), heavily
  documented, still common in production environments today.
- **3.x (chosen: 3.3.1)** — current stable release; the ecosystem is actively moving
  this direction (Airflow's own Helm chart now requires 2.11+ minimum). More relevant
  to demonstrate awareness of in a 2026 interview context.

**Executor for local development:**
- **CeleryExecutor (the shipped default)** — requires Redis + one or more worker
  containers. Designed to scale task execution across multiple machines.
- **LocalExecutor (chosen)** — scheduler runs tasks as subprocesses on the same machine.
  No queue, no separate worker service. Parallelism is bounded by the host's CPU cores.

## Decision
Use **Airflow 3.3.1** with **LocalExecutor**, obtained by downloading the official
CeleryExecutor quick-start `docker-compose.yaml` and removing the `redis`, `airflow-worker`,
and `flower` services, and switching `AIRFLOW__CORE__EXECUTOR` to `LocalExecutor`.

## Rationale
- Airflow 3.x reflects the current state of the ecosystem; building on 2.x now would
  mean learning a topology already being phased toward legacy status.
- Distributed task queuing (Redis + Celery workers) exists to scale execution across
  multiple machines. This project runs on a single laptop — that scaling need does not
  exist, so the infrastructure that exists to serve it is pure overhead: more containers
  to keep healthy, more failure surface, no corresponding benefit.
- LocalExecutor still preserves everything meaningful for this project's learning goals:
  DAG authoring, scheduling, retries, task dependencies, and the scheduler/dag-processor/
  api-server/triggerer split introduced in Airflow 3 (that split is independent of
  executor choice, so nothing about "why 4 services instead of 2" is lost).

## Consequences
- **Positive:** Fewer containers to run and reason about locally; faster startup; lower
  resource usage on a laptop; still demonstrates the current Airflow 3.x architecture.
- **Negative / Limitation:** LocalExecutor does not demonstrate distributed task
  execution, horizontal worker scaling, or Celery-specific operational concerns
  (queue depth, worker autoscaling, broker failure modes). If asked in an interview
  "have you run Airflow with CeleryExecutor," the honest answer is no — only
  LocalExecutor, with the trade-off understood conceptually, not hands-on.
- Parallelism is bounded by host CPU cores (`os.cpu_count()` on the scheduler container),
  not by number of worker machines — a real, stated limitation, not hidden.

## Future Considerations
- Production Azure evolution (Milestone 21) would likely map this to Azure-managed
  Airflow or self-hosted Airflow on AKS with `KubernetesExecutor` or `CeleryExecutor`,
  where the scaling need this ADR explicitly avoids locally becomes real. That mapping
  should reference this ADR rather than repeat its reasoning.
- The broader question — Airflow vs. non-Airflow orchestration alternatives entirely
  (Dagster, Prefect, plain cron, notebook orchestration) — is **not** addressed by this
  ADR and remains open. That is the scope of the originally-planned ADR-002 and should
  be written before it's cited as settled.