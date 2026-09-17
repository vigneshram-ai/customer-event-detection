# docker/train-job/Dockerfile
#
# Golden training-job image for Databricks Container Services (dedicated
# compute). Purpose: lock the training environment's system libraries to an
# immutable, version-pinned image instead of relying on Databricks' own
# environment/runtime churn.
#
# STATUS: DESIGNED ONLY — NEVER BUILT, NEVER RUN.
# This Dockerfile has not been built (`docker build` was never successfully
# run — Docker Desktop on the dev machine could not be gotten running
# reliably) and the image has never been pushed to a registry or launched as
# real Databricks Container Services compute. Databricks Free Edition only
# offers serverless compute, which does not support DCS (DCS requires
# classic/dedicated compute) anyway, so even a successful local build would
# not have closed that gap. Every claim in this file about what the image
# would contain is a design intent, not an observed result. See
# docs/adr/ADR-020-docker-container-services.md for full reasoning and
# status.
#
# BASE IMAGE VERSION NOTE (read before trusting this as a "verified match"):
# ced.training's live M8 pipeline runs on Databricks *serverless* environment
# version 5 (Ubuntu 24.04.3 LTS, Python 3.12.3, Databricks Connect 18 —
# confirmed Sept 2026). Serverless environment versions and classic
# Databricks Runtime version numbers are two separate, independently
# maintained numbering schemes with no official published mapping between
# them. 17.3 LTS is used below as the closest reasonable equivalent (current
# LTS release, Python 3.12-based) — this is an ASSUMPTION, not a verified
# compatibility match, and would need to be validated against a real DCS
# launch before being trusted in anything beyond a learning artifact.
FROM databricksruntime/standard:17.3-LTS

# Use the base image's own pip (not a system pip) per Databricks' documented
# convention for this base image family.
#
# Versions pinned below were read directly from the live training notebook
# via `%pip freeze` (Sept 2026) — not invented — so this image genuinely
# mirrors what M8's verified training run actually used, not an approximation.
RUN /databricks/python3/bin/pip install \
    mlflow-skinny==3.8.1 \
    pandas==2.2.3 \
    scikit-learn==1.6.1 \
    xgboost==3.4.1

# pyspark is intentionally NOT reinstalled here. It ships as part of the
# Databricks Runtime base image already; installing a different pyspark
# version on top risks breaking the runtime's own Spark/JVM integration.
#
# NOTE: Databricks ignores this image's CMD/ENTRYPOINT when launching real
# compute — the actual workload (training/train_model_job.py) is specified
# separately as a Databricks Job task, not baked into the image. Any CMD
# added here would only ever matter for local `docker run` sanity checks.