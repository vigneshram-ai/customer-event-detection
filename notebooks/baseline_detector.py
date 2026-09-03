# Databricks notebook source
# MAGIC %md
# MAGIC # Milestone 7: Baseline Rule-Based Detector
# MAGIC
# MAGIC Reads `ced.gold.customer_events_features`, applies a fixed, hand-reasoned
# MAGIC point-scoring rule set (no training, no fitting against ground truth —
# MAGIC see ADR-013), and writes per-event detection scores to
# MAGIC `ced.gold.baseline_detections`.
# MAGIC
# MAGIC This is a rule-based baseline, not the ML model. Its purposes:
# MAGIC 1. Establish the `model_version` / `detection_score` / `detection_flag`
# MAGIC    output contract that the eventual ML model and batch inference reuse.
# MAGIC 2. Provide a naive reference point the ML model must beat.
# MAGIC 3. Sanity-check the Milestone 6 Gold features against ground truth
# MAGIC    (evaluation happens separately, locally, against
# MAGIC    `events_ground_truth.csv` — not in this notebook).

# COMMAND ----------

from databricks.sdk.runtime import spark
from pyspark.sql import functions as F

CATALOG = "ced"
GOLD_FEATURES_TABLE = f"{CATALOG}.gold.customer_events_features"
OUTPUT_TABLE = f"{CATALOG}.gold.baseline_detections"

df = spark.table(GOLD_FEATURES_TABLE)
input_count = df.count()
print(f"Read {input_count} rows from {GOLD_FEATURES_TABLE}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Rule definitions
# MAGIC
# MAGIC Points are additive. Thresholds are fixed and reasoned (see ADR-013),
# MAGIC not tuned against ground truth. `amount_ratio` guards against NULL and
# MAGIC divide-by-zero (non-monetary events / customers with no prior monetary
# MAGIC history already have `prior_avg_amount_90d` = NULL from Milestone 6).

# COMMAND ----------

amount_ratio = F.when(
    F.col("prior_avg_amount_90d").isNotNull()
    & F.col("amount_deviation_from_prior_avg").isNotNull()
    & (F.col("prior_avg_amount_90d") != 0),
    F.abs(F.col("amount_deviation_from_prior_avg")) / F.col("prior_avg_amount_90d"),
).otherwise(F.lit(None))

scored = (
    df.withColumn("_amount_ratio", amount_ratio)
    .withColumn(
        "_pts_new_device",
        F.when(F.col("is_new_device"), F.lit(2)).otherwise(F.lit(0)),
    )
    .withColumn(
        "_pts_unusual_country",
        F.when(F.col("is_unusual_country"), F.lit(2)).otherwise(F.lit(0)),
    )
    .withColumn(
        "_pts_unusual_channel",
        F.when(F.col("is_unusual_channel"), F.lit(1)).otherwise(F.lit(0)),
    )
    .withColumn(
        "_pts_amount_tier1",
        F.when(F.col("_amount_ratio") > 2, F.lit(1)).otherwise(F.lit(0)),
    )
    .withColumn(
        "_pts_amount_tier2",
        F.when(F.col("_amount_ratio") > 5, F.lit(1)).otherwise(F.lit(0)),
    )
    .withColumn(
        "_pts_failed_login_tier1",
        F.when(F.col("prior_failed_login_count_24h") >= 3, F.lit(1)).otherwise(F.lit(0)),
    )
    .withColumn(
        "_pts_failed_login_tier2",
        F.when(F.col("prior_failed_login_count_24h") >= 6, F.lit(1)).otherwise(F.lit(0)),
    )
)

# COMMAND ----------

scored = scored.withColumn(
    "detection_score",
    F.col("_pts_new_device")
    + F.col("_pts_unusual_country")
    + F.col("_pts_unusual_channel")
    + F.col("_pts_amount_tier1")
    + F.col("_pts_amount_tier2")
    + F.col("_pts_failed_login_tier1")
    + F.col("_pts_failed_login_tier2"),
).withColumn("detection_flag", F.col("detection_score") >= 2)

reason_array = F.array(
    F.when(F.col("is_new_device"), F.lit("is_new_device")),
    F.when(F.col("is_unusual_country"), F.lit("is_unusual_country")),
    F.when(F.col("is_unusual_channel"), F.lit("is_unusual_channel")),
    F.when(F.col("_amount_ratio") > 2, F.lit("amount_deviation_tier1")),
    F.when(F.col("_amount_ratio") > 5, F.lit("amount_deviation_tier2")),
    F.when(F.col("prior_failed_login_count_24h") >= 3, F.lit("failed_login_tier1")),
    F.when(F.col("prior_failed_login_count_24h") >= 6, F.lit("failed_login_tier2")),
)

scored = scored.withColumn("reason", F.filter(reason_array, lambda x: x.isNotNull()))

# COMMAND ----------

result = scored.select(
    "customer_id",
    "event_id",
    "event_timestamp",
    "detection_score",
    "detection_flag",
    "reason",
    F.lit("baseline_rule_v1").alias("model_version"),
    F.current_timestamp().alias("scored_at"),
    F.col("prior_event_count_7d").alias("context_prior_event_count_7d"),
    F.col("time_since_last_event_seconds").alias("context_time_since_last_event_seconds"),
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Row-count reconciliation
# MAGIC
# MAGIC No quarantine/filtering at this layer, same convention as Gold — every
# MAGIC input row gets scored. A mismatch here is a bug, not a data-quality issue.

# COMMAND ----------

output_count = result.count()
assert output_count == input_count, (
    f"Row count mismatch: {input_count} input vs {output_count} output"
)
print(f"OK: {output_count} baseline detections reconcile exactly with {input_count} Gold rows.")

result.write.mode("overwrite").saveAsTable(OUTPUT_TABLE)
print(f"Wrote {output_count} rows to {OUTPUT_TABLE}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Sanity checks

# COMMAND ----------

written = spark.table(OUTPUT_TABLE)

written.groupBy("detection_score").count().orderBy("detection_score").show()

flag_count = written.filter(F.col("detection_flag")).count()
print(f"detection_flag = True: {flag_count} ({flag_count / output_count:.2%})")

reason_counts = (
    written.select(F.explode("reason").alias("rule"))
    .groupBy("rule")
    .count()
    .orderBy(F.desc("count"))
)
reason_counts.show(truncate=False)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Export for local evaluation
# MAGIC
# MAGIC Writes a flat CSV of baseline_detections to a Unity Catalog volume so a
# MAGIC local script (no Spark/Databricks-connect session) can download it and
# MAGIC join against `events_ground_truth.csv`. `reason` (array<string>) is
# MAGIC flattened to a `;`-delimited string for CSV portability.

# COMMAND ----------

spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.gold.exports")

export_df = written.withColumn("reason", F.array_join("reason", ";"))

export_pdf = export_df.select(
    "event_id",
    "customer_id",
    "detection_score",
    "detection_flag",
    "reason",
    "model_version",
).toPandas()

export_path = f"/Volumes/{CATALOG}/gold/exports/baseline_detections.csv"
export_pdf.to_csv(export_path, index=False)

print(f"Exported {len(export_pdf)} rows to {export_path}")
