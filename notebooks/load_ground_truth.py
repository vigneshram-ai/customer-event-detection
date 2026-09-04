# Databricks notebook source
# MAGIC %md
# MAGIC # Load Ground Truth Labels — ced.training
# MAGIC
# MAGIC Reads the Milestone 3 ground-truth sidecar CSV from
# MAGIC `/Volumes/ced/training/raw_labels/events_ground_truth.csv` and writes
# MAGIC `ced.training.ground_truth_labels` (`event_id`, `anomaly_type`, `is_anomaly`).
# MAGIC
# MAGIC Per ADR-014: this table is isolated in `ced.training`, which is never
# MAGIC joined into or read from `ced.gold` or any inference-facing table.

# COMMAND ----------

import pyspark.sql.functions as F
import pyspark.sql.types as T
from databricks.sdk.runtime import spark

CATALOG = "ced"
VOLUME_PATH = f"/Volumes/{CATALOG}/training/raw_labels/events_ground_truth.csv"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.training")

# COMMAND ----------

# Schema confirmed from actual CSV header: event_id, is_synthetic_anomaly, anomaly_type
raw_schema = T.StructType(
    [
        T.StructField("event_id", T.StringType(), False),
        T.StructField("is_synthetic_anomaly", T.StringType(), True),
        T.StructField("anomaly_type", T.StringType(), True),
    ]
)

df_raw = (
    spark.read.format("csv")
    .option("header", "true")
    .option("nullValue", "")
    .schema(raw_schema)
    .load(VOLUME_PATH)
)

# is_synthetic_anomaly is already the authoritative label — read and rename it,
# don't derive it from anomaly_type's nullability. anomaly_type is kept as-is
# (geo_deviation, channel_deviation, etc.) since train_model.py's recall_by_type
# groups on its exact values.
labels_df = df_raw.select(
    "event_id",
    "anomaly_type",
    F.col("is_synthetic_anomaly").cast("boolean").alias("is_anomaly"),
)

# COMMAND ----------

row_count = labels_df.count()
print(f"Loaded {row_count} ground-truth label rows from volume.")
labels_df.groupBy("anomaly_type").count().orderBy("anomaly_type").show(truncate=False)

# COMMAND ----------

(
    labels_df.write.format("delta")
    .mode("overwrite")
    .saveAsTable(f"{CATALOG}.training.ground_truth_labels")
)

written_count = spark.table(f"{CATALOG}.training.ground_truth_labels").count()
print(f"Wrote {written_count} rows to {CATALOG}.training.ground_truth_labels")
assert written_count == row_count, "Row count mismatch on write — investigate before proceeding."
