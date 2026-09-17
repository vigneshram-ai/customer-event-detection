# train-job Docker image

## What this is

A "golden container" for `train_model.py`'s training workload: a Docker image
extending Databricks' own runtime base (`databricksruntime/standard`),
with the exact ML package versions verified against the live `ced.training`
pipeline pinned in at build time. Purpose: demonstrate the "locked-down
environment, immune to platform runtime drift" pattern that Databricks
Container Services exists for — one of the three official DCS use cases
(library customization / golden container / Docker CI-CD integration).

## Verification status — read this before trusting anything below

| Claim | Status |
|---|---|
| Image builds successfully via `docker build` | 📐 DESIGNED ONLY — never run. Docker Desktop on the dev machine could not be kept running reliably (severe slowdowns/hangs); `docker build` was never successfully executed |
| Pinned packages import cleanly inside the container | 📐 DESIGNED ONLY — untested, same blocker |
| Image tag `17.3-LTS` is a *correct* stand-in for serverless environment 5 | ⚠️ ASSUMPTION — no official mapping exists between the two versioning schemes (see Dockerfile header) |
| Image successfully launches as real Databricks Container Services compute | 📐 DESIGNED ONLY — never attempted. Databricks Free Edition (this project's only workspace) offers serverless compute only; DCS requires classic/dedicated compute, which Free Edition does not offer at all |
| Image successfully authenticates to Unity Catalog / MLflow when run as a real DCS job | 📐 DESIGNED ONLY — untested |
| Image pushed to a Docker registry | Not done |

**Do not describe this image as "built," "tested," or "deployed" anywhere — none of
those happened.** Every artifact in `docker/train-job/` and `training/train_model_job.py`
is a designed, unexecuted learning artifact, documented in
`docs/adr/ADR-020-docker-container-services.md`. The `Dockerfile` and this
README describe *intent* (what would happen if built), not an observed result.

## Note on the Docker Desktop blocker

Docker Desktop on Windows became unusably slow / hung the machine, so even
the local build-and-smoke-test tier of verification (the one part of this
milestone that didn't depend on a paid Databricks tier) was never completed.
If verification is revisited later, installing the Docker **Engine** directly
inside the existing WSL2 distro (no Docker Desktop GUI) is generally much
lighter-weight and would reuse the WSL2 setup already in place for Airflow —
worth considering as a follow-up, not undertaken this milestone.

## Commands to build and verify locally

```bash
cd docker/train-job
docker build -t ced-train-job:local .

# Confirm the exact pinned versions actually landed in the image
docker run --rm ced-train-job:local /databricks/python3/bin/pip list

# Confirm the pinned packages import cleanly (proves the image is
# well-formed; does NOT prove Databricks integration — that requires a
# real job run, which this milestone deliberately does not attempt)
docker run --rm ced-train-job:local /databricks/python3/bin/python -c \
  "import mlflow, pandas, sklearn, xgboost; print('imports OK')"
```

## Expected results

- `docker build` completes without error.
- `pip list` shows `mlflow-skinny 3.8.1`, `pandas 2.2.3`, `scikit-learn 1.6.1`,
  `xgboost 3.4.1`, plus whatever `pyspark`/JVM tooling ships with the
  `databricksruntime/standard:17.3-LTS` base.
- The import check prints `imports OK`.

## What would be needed to actually move this to DESIGNED → IMPLEMENTED

1. A Docker registry to push to (Docker Hub free tier is sufficient).
2. A Databricks workspace with classic/dedicated compute — not available on
   Free Edition. A time-boxed 14-day trial workspace was considered for this
   milestone and explicitly declined (see ADR-020) in favor of keeping this
   as a documented learning artifact rather than a throwaway verified run.
3. `databricks clusters create` (or the Jobs API equivalent) with a
   `docker_image` block pointing at the pushed image, plus a
   `spark_python_task` pointing at `training/train_model_job.py`.
4. Databricks Container Services enabled on that workspace
   (`databricks workspace-conf set-status --json '{"enableDcs": "true"}'`).