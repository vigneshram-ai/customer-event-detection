# ADR-020: Docker Container Services for Training (Designed, Not Deployed)

## Status
Designed only. Not implemented, not deployed, not verified beyond initial
research. Milestone 15.

## Context

The project's target resume statement claims Docker as part of the stack.
Prior milestones had explicitly and correctly rejected Docker twice:

- **ADR-018** moved Airflow *off* Docker onto WSL2-native execution, because
  `DatabricksSubmitRunOperator` + Free Edition serverless compute had
  compatibility issues that were easier to resolve running Airflow natively.
- **ADR-019** rejected adding a Docker CI stage, because nothing in the
  architecture was containerized — adding one "to satisfy the word CD" would
  have been technology without genuine purpose.

Neither rejection is reopened by this ADR. This milestone asked a narrower
question: is there a component with a genuine, non-contrived reason to be
containerized, distinct from what was already correctly ruled out.

## Problem

Databricks notebooks execute inside the Databricks runtime itself — Docker
doesn't apply there directly, except via **Databricks Container Services
(DCS)**, which lets a cluster's *system libraries* be defined by a custom
Docker image instead of Databricks' own environment/runtime versioning. This
is a real, documented Databricks feature with a real use case: a "golden,"
version-locked training environment immune to platform runtime drift.

The catch: DCS requires classic/dedicated compute. Databricks Free
Edition — this project's only workspace — offers **serverless compute only**,
and does not support DCS at all. There is no way to actually launch this on
the workspace this project has used for every other milestone.

## Options Considered

1. **Containerize a client-side script that calls Databricks via SDK/REST**
   (e.g. the synthetic data generator, or the M14 CI smoke-test script).
   This runs *outside* Databricks and would have been fully buildable,
   runnable, and verifiable on Free Edition with zero blockers. Rejected
   for this milestone in favor of option 3, at the user's explicit
   direction, because it doesn't touch DCS — the specific Databricks
   feature the user wanted to learn.
2. **Spin up a time-boxed (14-day) free trial Databricks workspace with
   classic compute enabled, and actually deploy and verify DCS end-to-end.**
   Explicitly declined by the user in favor of keeping this a documented
   design exercise rather than a throwaway verified run.
3. **Design and build the DCS path for the actual training workload
   (`train_model.py`), understand and document the mechanics in depth, and
   explicitly mark deployment as unverified rather than pretend otherwise.**
   **Chosen.**

## Decision

Build the container/job design for re-platforming `train_model.py`'s
training workload onto DCS-backed classic compute, as a learning artifact:

- `docker/train-job/Dockerfile` — extends `databricksruntime/standard`,
  pins the exact package versions read from the live training notebook's
  `%pip freeze` output (`mlflow-skinny==3.8.1`, `pandas==2.2.3`,
  `scikit-learn==1.6.1`, `xgboost==3.4.1`), does not reinstall `pyspark`.
- `training/train_model_job.py` — a script-task adaptation of the real,
  verified `notebooks/train_model.py` (M8), with exactly two changes:
  removing the `%pip install xgboost` + `dbutils.library.restartPython()`
  cell (obsoleted by the image baking xgboost in at build time), and
  replacing the notebook-specific `databricks.sdk.runtime` import of `spark`
  with `SparkSession.builder.getOrCreate()` (the documented pattern for
  non-notebook Databricks Job script tasks). Every other line — feature
  columns, the in-memory join and its ADR-014 row-count assertion, the
  stratified split, the baseline reference run, both training runs, the
  registered model names — is unchanged from the verified M8 source.
- `scripts/dcs_job_spec.json` — an annotated Databricks Jobs API payload
  (new-cluster `docker_image` block + `spark_python_task`), with every
  placeholder and unverified assumption called out inline via `_*_note`
  keys that must be stripped before the file would be a valid API payload.

## Rationale

This gives genuine, defensible depth on a real Databricks feature (DCS)
without misrepresenting what was actually verified. The training workload
was chosen over inference or the generator because "lock the environment so
it's immune to platform drift" is a materially stronger, more specific
argument for *training* specifically than for a lighter-weight script.

## Consequences

- **Nothing in this ADR's scope changes the live, working pipeline.** The
  real Airflow-orchestrated training path still runs `notebooks/train_model.py`
  as a notebook on serverless compute, exactly as verified in M8. This ADR
  adds a parallel, undeployed design artifact — it does not replace anything.
- The resume-statement Docker gap identified at the start of M15 is now
  **partially closed**: Docker was genuinely designed and reasoned about in
  depth against a real Databricks feature, but **not built, not run, and not
  deployed** — the local build itself was blocked by Docker Desktop
  performance problems on the dev machine (never resolved this milestone),
  and DCS deployment was never in scope per the option chosen above. Any
  resume/interview claim about this work must say "designed" or "learned the
  DCS deployment model for," never "implemented," "built," or "deployed."
- The single largest unverified assumption in this whole design is whether
  `SINGLE_USER` access mode + `docker_image` + Unity Catalog table access
  actually combine cleanly on real DCS compute — flagged explicitly in
  `scripts/dcs_job_spec.json` rather than asserted as fact.
- If this is picked up again later: installing Docker Engine directly inside
  the project's existing WSL2 distro (bypassing Docker Desktop's GUI/VM
  overhead) is the most promising unblocking path for at least reaching the
  local-build verification tier, without needing a paid or trial Databricks
  workspace.

## Future Considerations

- Actually building and smoke-testing the image locally (blocked this
  milestone by Docker Desktop performance, not by architecture).
- Actually submitting `scripts/dcs_job_spec.json` against a real
  classic-compute workspace (trial or paid) to move any part of this from
  DESIGNED to IMPLEMENTED & VERIFIED.
- If DCS is ever genuinely adopted: deciding whether it *replaces*
  `notebooks/train_model.py`'s notebook-based execution or exists alongside
  it — not decided here, since nothing has actually run yet to inform that
  choice.