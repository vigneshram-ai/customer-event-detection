# Databricks notebook source
# MAGIC %md
# MAGIC # Milestone 10 — Batch Inference
# MAGIC
# MAGIC Loads `ced.models.logistic_regression_detector@champion`, scores a
# MAGIC reproducible sample of `ced.gold.customer_events_features`, and writes
# MAGIC results to `ced.inference.detection_results`.
# MAGIC
# MAGIC Scope note (see ADR-016): this batch is a random sample of existing Gold
# MAGIC data, not genuinely new/unseen events and not the M8 held-out test split.
# MAGIC It demonstrates the batch-inference mechanism (alias-based model
# MAGIC loading, scoring, contract output) — it is not a model performance
# MAGIC evaluation. That already happened properly in Milestone 8.

# COMMAND ----------

import mlflow
from databricks.sdk.runtime import spark
from mlflow.tracking import MlflowClient
from pyspark.sql import functions as F

mlflow.set_registry_uri("databricks-uc")

MODEL_NAME = "ced.models.logistic_regression_detector"
ALIAS = "champion"
SAMPLE_SIZE = 500
SAMPLE_SEED = 42

FEATURE_COLUMNS = [
    "prior_event_count_7d",
    "prior_avg_amount_90d",
    "amount_deviation_from_prior_avg",
    "is_new_device",
    "is_unusual_channel",
    "is_unusual_country",
    "prior_failed_login_count_24h",
    "time_since_last_event_seconds",
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resolve the champion version and load via pyfunc
# MAGIC
# MAGIC We resolve the concrete version number behind the alias *now*, at
# MAGIC scoring time, and stamp every output row with it. If `champion` moves
# MAGIC to a different version later, already-written detection records still
# MAGIC honestly reflect what produced them.
# MAGIC
# MAGIC We load via `mlflow.pyfunc.load_model` — the generic, flavor-agnostic
# MAGIC interface, same one `mlflow.pyfunc.spark_udf` uses for distributed
# MAGIC scoring. That generic interface's `.predict()` returns the sklearn
# MAGIC model's class label (0/1), not a probability — there's no
# MAGIC flavor-agnostic "give me predict_proba." To get a continuous
# MAGIC `detection_score`, we unwrap the sklearn estimator out of the pyfunc
# MAGIC wrapper via `_model_impl.sklearn_model`. This is a documented
# MAGIC limitation, not a generic pattern: a genuinely distributed,
# MAGIC flavor-agnostic probability score would require the model to be
# MAGIC logged at training time as a custom `PythonModel` whose `predict()`
# MAGIC itself returns probabilities — out of scope for this milestone, see
# MAGIC ADR-016.

# COMMAND ----------

client = MlflowClient()
champion_version = client.get_model_version_by_alias(MODEL_NAME, ALIAS)
resolved_model_version = f"logistic_regression_detector_v{champion_version.version}"

print(f"Resolved {MODEL_NAME}@{ALIAS} -> version {champion_version.version}")
print(f"model_version to be written: {resolved_model_version}")

model_uri = f"models:/{MODEL_NAME}@{ALIAS}"
pyfunc_model = mlflow.pyfunc.load_model(model_uri)

# Unwrap to reach predict_proba — see note above.
# Fails loudly (rather than silently returning class labels) if the
# champion model is ever not an sklearn flavor.
if not hasattr(pyfunc_model._model_impl, "sklearn_model"):
    raise TypeError(
        "Loaded model is not the expected sklearn flavor — "
        "the _model_impl.sklearn_model unwrap path is sklearn-specific "
        "and won't work here. Update the scoring logic for the actual "
        "flavor in use."
    )

sk_model = pyfunc_model._model_impl.sklearn_model

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sample the batch to score
# MAGIC
# MAGIC Reproducible random sample of existing Gold features (seeded), not a
# MAGIC genuinely new event batch. See ADR-016 for why.

# COMMAND ----------

gold_df = spark.table("ced.gold.customer_events_features")

batch_df = gold_df.orderBy(F.rand(SAMPLE_SEED)).limit(SAMPLE_SIZE)

batch_count = batch_df.count()
print(f"Batch size to score: {batch_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Score the batch
# MAGIC
# MAGIC Pull to a pandas DataFrame for sklearn scoring (500 rows — fine at
# MAGIC this scale; a genuinely large batch would need a Spark-native /
# MAGIC pandas-UDF scoring path instead, a scalability note for the future).

# COMMAND ----------

pdf = batch_df.select("customer_id", "event_id", "event_timestamp", *FEATURE_COLUMNS).toPandas()

# Matches train_model.py's preprocessing exactly (fillna(0) on the same
# FEATURE_COLS). This is required for train/serve parity, not because 0
# is semantically ideal — amount-based features are NULL both when a row
# is non-monetary (structural, ADR-012) and when a monetary row simply
# has no prior history, and filling both with 0 conflates the two. That
# ambiguity was already baked into the champion model's coefficients at
# training time (M8); replicating it here is correct even though the
# underlying imputation choice is a documented limitation, not an
# endorsement. See ADR-016 / technical debt.
X = pdf[FEATURE_COLUMNS].fillna(0)

detection_scores = sk_model.predict_proba(X)[:, 1]
pdf["detection_score"] = detection_scores
pdf["detection_flag"] = pdf["detection_score"] >= 0.5
pdf["model_version"] = resolved_model_version

print(pdf[["customer_id", "event_id", "detection_score", "detection_flag"]].head(10))
print(
    f"\nFlagged {int(pdf['detection_flag'].sum())} of {len(pdf)} scored events "
    f"({pdf['detection_flag'].mean():.2%})"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write detection results

# COMMAND ----------

output_columns = [
    "customer_id",
    "event_id",
    "event_timestamp",
    "model_version",
    "detection_score",
    "detection_flag",
] + FEATURE_COLUMNS

results_df = spark.createDataFrame(pdf[output_columns]).withColumn(
    "scored_at", F.current_timestamp()
)

(results_df.write.format("delta").mode("overwrite").saveAsTable("ced.inference.detection_results"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify

# COMMAND ----------

written = spark.table("ced.inference.detection_results")
print(f"Rows in ced.inference.detection_results: {written.count()}")
written.groupBy("model_version", "detection_flag").count().show()
