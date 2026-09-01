# Databricks notebook source
# MAGIC %md
# MAGIC # Silver Transformation — Customer Event Detection
# MAGIC Reads Bronze Delta tables (`ced.bronze.customers`, `ced.bronze.events`) written by
# MAGIC Milestone 4's `bronze_ingestion.py`, validates them with PySpark-native checks, and
# MAGIC splits each into a clean Silver table plus a rejects table.
# MAGIC
# MAGIC ### Design principles
# MAGIC - **Quarantine, not hard-fail.** Every input row lands somewhere: `ced.silver.<table>`
# MAGIC   if it passes all rules, `ced.silver.<table>_rejects` if it fails any. Nothing is
# MAGIC   silently dropped. This is an enforcement point and audit trail, not a pipeline
# MAGIC   circuit-breaker — there is no orchestrator yet (Airflow wiring is Milestone 12)
# MAGIC   to actually halt downstream work on a bad batch.
# MAGIC - **Validation logic is plain PySpark** (`filter`, `isNull`, `when`/`otherwise`,
# MAGIC   window functions) — no Great Expectations / Pandera. Consistent with Bronze's
# MAGIC   manual-check style; avoids a second validation framework for a single-user,
# MAGIC   27K-row dataset. See ADR-011 for the full trade-off writeup.
# MAGIC - **Customers are validated and split before events.** Events' referential-integrity
# MAGIC   check uses the *cleaned* `ced.silver.customers` (not raw Bronze) as the valid
# MAGIC   `customer_id` set — an event referencing an already-rejected customer is itself
# MAGIC   rejected, rather than silently passing through on a bad foreign key.
# MAGIC - **`event_timestamp` is parsed here** (Bronze deliberately keeps it as `StringType`).
# MAGIC   Rows where parsing fails are quarantined, not silently nulled.
# MAGIC - **`merchant_category` NULL is not automatically a violation.** It's the expected,
# MAGIC   valid value for the 6 non-monetary event types. It's only flagged when NULL on a
# MAGIC   monetary event type (`card_transaction`/`payment`/`transfer`), where it should be
# MAGIC   populated. Resolves the Milestone 4 known-limitation note in ADR-010.
# MAGIC - A row can fail more than one rule at once (e.g. bad `event_type` *and* bad
# MAGIC   `amount`). `_rejection_reasons` is an array so every reason is captured, not just
# MAGIC   the first one matched.

# COMMAND ----------

from databricks.sdk.runtime import display, spark
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

CATALOG = "ced"
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"

EVENT_TYPES = [
    "card_transaction",
    "login",
    "payment",
    "transfer",
    "failed_login",
    "beneficiary_added",
    "device_changed",
    "password_changed",
    "profile_changed",
]
MONETARY_EVENT_TYPES = ["card_transaction", "payment", "transfer"]

# COMMAND ----------


def _split_on_reasons(
    df: DataFrame, reasons_col: str = "_rejection_reasons"
) -> tuple[DataFrame, DataFrame]:
    """Split a DataFrame carrying a `_rejection_reasons` array column into
    (valid, rejects) based on whether that array is empty.

    Adds `_validated_at` to both outputs for audit purposes.
    """
    df = df.withColumn("_validated_at", F.current_timestamp())
    valid = df.filter(F.size(F.col(reasons_col)) == 0).drop(reasons_col)
    rejects = df.filter(F.size(F.col(reasons_col)) > 0)
    return valid, rejects


# COMMAND ----------


def validate_customers(bronze_df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Apply Silver-layer quality rules to Bronze customers, returning (valid, rejects).

    Rules:
      - required fields non-null: customer_id, account_age_days, home_country,
        normal_channel, normal_device
      - account_age_days >= 0
      - customer_id must be unique (all rows sharing a duplicated id are rejected --
        we cannot determine which copy, if any, is correct)
    """
    id_counts = Window.partitionBy("customer_id")

    df = bronze_df.withColumn("_dup_count", F.count("customer_id").over(id_counts))

    reasons = F.array_compact(
        F.array(
            F.when(F.col("customer_id").isNull(), F.lit("null_customer_id")),
            F.when(F.col("account_age_days").isNull(), F.lit("null_account_age_days")),
            F.when(F.col("account_age_days") < 0, F.lit("negative_account_age_days")),
            F.when(F.col("home_country").isNull(), F.lit("null_home_country")),
            F.when(F.col("normal_channel").isNull(), F.lit("null_normal_channel")),
            F.when(F.col("normal_device").isNull(), F.lit("null_normal_device")),
            F.when(F.col("_dup_count") > 1, F.lit("duplicate_customer_id")),
        )
    )

    df = df.withColumn("_rejection_reasons", reasons).drop("_dup_count")
    return _split_on_reasons(df)


# COMMAND ----------


def validate_events(
    bronze_df: DataFrame, valid_customer_ids: DataFrame
) -> tuple[DataFrame, DataFrame]:
    """Apply Silver-layer quality rules to Bronze events, returning (valid, rejects).

    Rules:
      - required fields non-null: event_id, customer_id, event_type
      - event_timestamp must parse to a valid TimestampType
      - event_type must be one of the 9 known values
      - amount must be non-null and > 0 for monetary event types
      - amount must be null OR 0.0 for non-monetary event types. NOTE: this is a
        deliberate relaxation, not the architecturally preferred design. The M3
        generator writes a literal 0.0 (not NULL) as its default for non-monetary
        amount, unlike merchant_category which correctly defaults to NULL (see
        ADR-010). Accepting 0.0 here avoids touching an already-verified milestone,
        but it means "not applicable" and "genuinely zero" are indistinguishable
        for amount from Silver onward -- a real cost if amount_spike-style feature
        engineering (Milestone 6+) ever needs that distinction. Tracked as technical
        debt; revisit by fixing the generator if it becomes a real blocker.
      - merchant_category must be non-null for monetary event types (null is valid
        and expected for non-monetary event types -- not flagged)
      - event_id must be unique
      - customer_id must exist in the cleaned (Silver) customers set
    """
    # Generator writes datetime.isoformat() output, e.g. "2026-01-14T13:08:48" --
    # ISO 8601, second precision, no timezone. Format pinned explicitly rather than
    # relying on to_timestamp()'s auto-detection, so a future change in the
    # generator's timestamp precision/format fails loudly (as unparseable rows in
    # the rejects table) instead of silently drifting.
    TIMESTAMP_FORMAT = "yyyy-MM-dd'T'HH:mm:ss"
    df = bronze_df.withColumn(
        "event_timestamp_parsed", F.to_timestamp(F.col("event_timestamp"), TIMESTAMP_FORMAT)
    )

    event_id_counts = Window.partitionBy("event_id")
    df = df.withColumn("_dup_count", F.count("event_id").over(event_id_counts))

    is_monetary = F.col("event_type").isin(MONETARY_EVENT_TYPES)

    df = df.join(
        valid_customer_ids.withColumnRenamed("customer_id", "_valid_customer_id"),
        df.customer_id == F.col("_valid_customer_id"),
        how="left",
    )

    reasons = F.array_compact(
        F.array(
            F.when(F.col("event_id").isNull(), F.lit("null_event_id")),
            F.when(F.col("customer_id").isNull(), F.lit("null_customer_id")),
            F.when(F.col("event_type").isNull(), F.lit("null_event_type")),
            F.when(
                F.col("event_type").isNotNull() & ~F.col("event_type").isin(EVENT_TYPES),
                F.lit("invalid_event_type"),
            ),
            F.when(F.col("event_timestamp_parsed").isNull(), F.lit("timestamp_unparseable")),
            F.when(
                is_monetary & F.col("amount").isNull(), F.lit("missing_amount_for_monetary_event")
            ),
            F.when(is_monetary & (F.col("amount") <= 0), F.lit("non_positive_amount")),
            F.when(
                ~is_monetary & F.col("amount").isNotNull() & (F.col("amount") != 0.0),
                F.lit("amount_present_for_non_monetary_event"),
            ),
            F.when(
                is_monetary & F.col("merchant_category").isNull(),
                F.lit("missing_merchant_category_for_monetary_event"),
            ),
            F.when(F.col("_dup_count") > 1, F.lit("duplicate_event_id")),
            F.when(
                F.col("customer_id").isNotNull() & F.col("_valid_customer_id").isNull(),
                F.lit("customer_id_not_in_silver_customers"),
            ),
        )
    )

    df = (
        df.withColumn("_rejection_reasons", reasons)
        .drop("_dup_count", "_valid_customer_id", "event_timestamp")
        .withColumnRenamed("event_timestamp_parsed", "event_timestamp")
    )
    return _split_on_reasons(df)


# COMMAND ----------


def write_silver_tables(
    valid_df: DataFrame,
    rejects_df: DataFrame,
    table_name: str,
    input_row_count: int,
) -> None:
    """Write the valid/rejects split to Silver Delta tables, then reconcile row
    counts: valid + rejects written must equal the Bronze input count, or we
    silently lost or duplicated rows during the join/window operations above.
    """
    valid_table = f"{CATALOG}.{SILVER_SCHEMA}.{table_name}"
    rejects_table = f"{CATALOG}.{SILVER_SCHEMA}.{table_name}_rejects"

    valid_df.write.mode("overwrite").saveAsTable(valid_table)
    rejects_df.write.mode("overwrite").saveAsTable(rejects_table)

    valid_count = spark.table(valid_table).count()
    rejects_count = spark.table(rejects_table).count()

    if valid_count + rejects_count != input_row_count:
        raise ValueError(
            f"Row count reconciliation failed for {table_name}: "
            f"input={input_row_count}, valid={valid_count}, rejects={rejects_count}, "
            f"sum={valid_count + rejects_count}."
        )

    print(
        f"OK: {valid_table} -- {valid_count:,} valid, "
        f"{rejects_table} -- {rejects_count:,} rejected "
        f"({rejects_count / input_row_count:.2%} reject rate)"
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## Customers: validate and write

# COMMAND ----------

bronze_customers = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.customers")
bronze_customers_count = bronze_customers.count()

silver_customers, silver_customers_rejects = validate_customers(bronze_customers)

write_silver_tables(silver_customers, silver_customers_rejects, "customers", bronze_customers_count)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Events: validate and write
# MAGIC Uses the *cleaned* `ced.silver.customers` (just written above) as the valid
# MAGIC `customer_id` set for referential integrity -- not raw Bronze.

# COMMAND ----------

bronze_events = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.events")
bronze_events_count = bronze_events.count()

valid_customer_ids = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.customers").select("customer_id")

silver_events, silver_events_rejects = validate_events(bronze_events, valid_customer_ids)

write_silver_tables(silver_events, silver_events_rejects, "events", bronze_events_count)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification queries
# MAGIC Run the cells below after the validation/write cells above complete successfully.

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SILVER_SCHEMA}.customers"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SILVER_SCHEMA}.events"))

# COMMAND ----------

# MAGIC %md
# MAGIC Breakdown of rejection reasons for events -- sanity-check that the rejects look
# MAGIC like genuine data-quality issues, not a systematic bug (e.g. every row rejected
# MAGIC for `timestamp_unparseable` would indicate the format-less `to_timestamp()` call
# MAGIC doesn't match the generator's actual timestamp string format).

# COMMAND ----------

display(
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.events_rejects")
    .select(F.explode("_rejection_reasons").alias("reason"))
    .groupBy("reason")
    .count()
    .orderBy(F.desc("count"))
)

# COMMAND ----------

display(
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.customers_rejects")
    .select(F.explode("_rejection_reasons").alias("reason"))
    .groupBy("reason")
    .count()
    .orderBy(F.desc("count"))
)

# COMMAND ----------

display(spark.sql(f"SELECT * FROM {CATALOG}.{SILVER_SCHEMA}.events LIMIT 5"))
