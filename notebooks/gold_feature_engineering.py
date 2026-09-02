# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Layer — Customer Event Feature Engineering
# MAGIC
# MAGIC **Milestone 6.** Reads validated `ced.silver.customers` and `ced.silver.events`,
# MAGIC computes behavioral features per event using PySpark window functions, and writes
# MAGIC one row per Silver event to `ced.gold.customer_events_features`.
# MAGIC
# MAGIC ## Leakage rule
# MAGIC Every rolling/window feature is computed using **only events strictly before**
# MAGIC the current row (`rowsBetween`/`rangeBetween` ending at `-1`, or `lag()`).
# MAGIC The current event never contributes to its own historical feature values.
# MAGIC
# MAGIC ## Features (Milestone 6 — full set, all folded into this milestone)
# MAGIC 1. `prior_event_count_7d` — rolling 7-day event count (velocity)
# MAGIC 2. `prior_avg_amount_90d` — rolling 90-day avg amount, monetary event types only
# MAGIC 3. `amount_deviation_from_prior_avg`—amount minus (2), monetary events only, NULL otherwise
# MAGIC 4. `is_new_device` — device is neither the customer's normal_device nor previously observed
# MAGIC 5. `is_unusual_channel` — channel differs from customer's normal_channel
# MAGIC 6. `is_unusual_country` — event country differs from customer's home_country
# MAGIC 7. `prior_failed_login_count_24h` — rolling 24h count of failed_login events,
# MAGIC    applies to every row regardless of current event's own type
# MAGIC 8. `time_since_last_event_seconds` — seconds since this customer's previous event
# MAGIC
# MAGIC Time-of-day deviation was considered and deliberately dropped from this
# MAGIC milestone — see docs/adr for rationale (circular-statistics complexity
# MAGIC wasn't justified without a concrete downstream need for it yet).

# COMMAND ----------

from databricks.sdk.runtime import display, spark
from pyspark.sql import Window
from pyspark.sql import functions as F

CATALOG = "ced"

MONETARY_EVENT_TYPES = ["card_transaction", "payment", "transfer"]

SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60
NINETY_DAYS_SECONDS = 90 * 24 * 60 * 60
TWENTY_FOUR_HOURS_SECONDS = 24 * 60 * 60

# COMMAND ----------

# MAGIC %md ## Load Silver inputs

# COMMAND ----------

silver_customers = spark.table(f"{CATALOG}.silver.customers")
silver_events = spark.table(f"{CATALOG}.silver.events")

silver_events_count = silver_events.count()
print(f"Silver events (input): {silver_events_count}")

# COMMAND ----------

# MAGIC %md ## Join customer context onto events
# MAGIC
# MAGIC Pulls in `normal_channel`, `normal_device`, `home_country`, `account_age_days`
# MAGIC — needed for the unusual-channel and new-device indicators.

# COMMAND ----------

events_with_customer = silver_events.join(
    silver_customers.select(
        "customer_id",
        "home_country",
        "normal_channel",
        "normal_device",
        "account_age_days",
    ),
    on="customer_id",
    how="inner",
)

# Inner join is intentional and safe here: Silver's referential-integrity check
# (Milestone 5) already guarantees every Silver event's customer_id exists in
# Silver customers. An inner join should therefore drop zero rows — verified
# below rather than assumed.
joined_count = events_with_customer.count()
if joined_count != silver_events_count:
    raise ValueError(
        f"Join dropped rows unexpectedly: {silver_events_count} Silver events -> "
        f"{joined_count} after joining customer context. Silver's referential "
        f"integrity guarantee should make this impossible — investigate before proceeding."
    )
print(f"Events after customer join: {joined_count} (matches Silver input)")

# COMMAND ----------

# MAGIC %md ## Prepare timestamp-as-seconds for time-bounded windows
# MAGIC
# MAGIC `rangeBetween` on a time-bounded window needs a numeric column, not a
# MAGIC `TimestampType` directly — cast to unix epoch seconds for the range windows.

# COMMAND ----------

events_prepared = events_with_customer.withColumn(
    "_event_ts_seconds", F.col("event_timestamp").cast("long")
)

# COMMAND ----------

# MAGIC %md ## Feature 1 — `prior_event_count_7d`
# MAGIC
# MAGIC Rolling count of this customer's events in the preceding 7 days.
# MAGIC Time-bounded range window, ending at `-1` second (strictly before the
# MAGIC current event's timestamp) so simultaneous-timestamp edge cases don't
# MAGIC count the current row.

# COMMAND ----------

window_7d = (
    Window.partitionBy("customer_id")
    .orderBy("_event_ts_seconds")
    .rangeBetween(-SEVEN_DAYS_SECONDS, -1)
)

events_prepared = events_prepared.withColumn(
    "prior_event_count_7d", F.count("event_id").over(window_7d)
)

# COMMAND ----------

# MAGIC %md ## Features 2 & 3 — `prior_avg_amount_90d`, `amount_deviation_from_prior_avg`
# MAGIC
# MAGIC **ADR-011 interaction:** the Silver `amount = 0.0` sentinel for non-monetary
# MAGIC events would silently drag rolling averages toward zero if included. Fixed
# MAGIC here by filtering on `event_type` (monetary types only), not on the `amount`
# MAGIC value itself — a genuine `amount = 0.0` on a monetary event still counts
# MAGIC correctly. Non-monetary events get `NULL` for both features, distinguishing
# MAGIC "not applicable" from "zero deviation" — the ambiguity Silver could not
# MAGIC resolve at the row level is resolved here at the feature level.

# COMMAND ----------

window_90d = (
    Window.partitionBy("customer_id")
    .orderBy("_event_ts_seconds")
    .rangeBetween(-NINETY_DAYS_SECONDS, -1)
)

# Only monetary-event amounts feed the rolling average; non-monetary rows
# contribute NULL to the window's input, which avg() ignores automatically.
monetary_amount_for_window = F.when(
    F.col("event_type").isin(MONETARY_EVENT_TYPES), F.col("amount")
).otherwise(F.lit(None).cast("double"))

# The window itself only ever averages monetary amounts (non-monetary rows
# contribute NULL to the window's input, so avg() ignores them). But the
# resulting value is still computed for every row, regardless of the current
# row's own event_type -- a `login` event would otherwise get a real "customer's
# recent monetary average" figure instead of NULL. Gate on the current row's
# event_type too, so both amount-based features share one applicability rule:
# NULL whenever the current event isn't monetary, full stop.
events_prepared = events_prepared.withColumn(
    "_prior_avg_amount_90d_raw", F.avg(monetary_amount_for_window).over(window_90d)
)

events_prepared = events_prepared.withColumn(
    "prior_avg_amount_90d",
    F.when(
        F.col("event_type").isin(MONETARY_EVENT_TYPES),
        F.col("_prior_avg_amount_90d_raw"),
    ).otherwise(F.lit(None).cast("double")),
)

events_prepared = events_prepared.withColumn(
    "amount_deviation_from_prior_avg",
    F.when(
        F.col("event_type").isin(MONETARY_EVENT_TYPES),
        F.col("amount") - F.col("_prior_avg_amount_90d_raw"),
    ).otherwise(F.lit(None).cast("double")),
)

events_prepared = events_prepared.drop("_prior_avg_amount_90d_raw")

# COMMAND ----------

# MAGIC %md ## Feature 4 — `is_new_device`
# MAGIC
# MAGIC `False` if the device is the customer's declared `normal_device`, OR if it
# MAGIC appears anywhere in that customer's prior event history. `True` only when
# MAGIC neither is the case. Uses an unbounded-preceding row window with
# MAGIC `collect_set` to build the "devices seen so far" set at each row.

# COMMAND ----------

window_all_prior = (
    Window.partitionBy("customer_id")
    .orderBy("_event_ts_seconds")
    .rowsBetween(Window.unboundedPreceding, -1)
)

events_prepared = events_prepared.withColumn(
    "_prior_devices_seen", F.collect_set("device_id").over(window_all_prior)
)

events_prepared = events_prepared.withColumn(
    "is_new_device",
    ~(
        (F.col("device_id") == F.col("normal_device"))
        | F.array_contains(F.col("_prior_devices_seen"), F.col("device_id"))
    ),
)

events_prepared = events_prepared.drop("_prior_devices_seen")

# COMMAND ----------

# MAGIC %md ## Feature 5 — `is_unusual_channel`
# MAGIC
# MAGIC Simple comparison against the customer's declared normal channel — no
# MAGIC window function needed.

# COMMAND ----------

events_prepared = events_prepared.withColumn(
    "is_unusual_channel", F.col("channel") != F.col("normal_channel")
)

# COMMAND ----------

# MAGIC %md ## Feature 6 — `is_unusual_country`
# MAGIC
# MAGIC Simple comparison against the customer's `home_country` — same pattern as
# MAGIC `is_unusual_channel`. Country-level mismatch, not true geographic distance
# MAGIC (the data model has no lat/long) — an honest proxy for "geographic
# MAGIC deviation" given what's actually available, not a claim of precise
# MAGIC geo-distance calculation.

# COMMAND ----------

events_prepared = events_prepared.withColumn(
    "is_unusual_country", F.col("country") != F.col("home_country")
)

# COMMAND ----------

# MAGIC %md ## Feature 7 — `prior_failed_login_count_24h`
# MAGIC
# MAGIC Rolling 24-hour count of `failed_login` events, same time-bounded-window
# MAGIC pattern as `prior_event_count_7d` but filtered to one event type and a
# MAGIC shorter horizon. Unlike the amount features, this is **not** gated to only
# MAGIC populate when the current row is itself a `failed_login` — a burst of
# MAGIC failed logins is relevant context for any subsequent event (e.g. a payment
# MAGIC right after several failed logins), so it's computed on every row.

# COMMAND ----------

window_24h = (
    Window.partitionBy("customer_id")
    .orderBy("_event_ts_seconds")
    .rangeBetween(-TWENTY_FOUR_HOURS_SECONDS, -1)
)

failed_login_indicator = F.when(F.col("event_type") == "failed_login", 1).otherwise(0)

# Spark's SUM over an empty window frame (no rows in range) returns NULL, not
# the identity value 0 -- even though "zero failed logins in the past 24h" is
# a known fact, not missing information, whenever a customer has no prior
# events in that window (including their very first event). Coalesce to 0 so
# the column means what it says: a count, never "unknown."
events_prepared = events_prepared.withColumn(
    "prior_failed_login_count_24h",
    F.coalesce(F.sum(failed_login_indicator).over(window_24h), F.lit(0)),
)

# COMMAND ----------

# MAGIC %md ## Feature 8 — `time_since_last_event_seconds`
# MAGIC
# MAGIC Seconds since this customer's immediately preceding event, via `lag()`.
# MAGIC `NULL` for a customer's first-ever event (no prior event exists).

# COMMAND ----------

customer_order_window = Window.partitionBy("customer_id").orderBy("_event_ts_seconds")

events_prepared = events_prepared.withColumn(
    "_prior_event_ts_seconds", F.lag("_event_ts_seconds").over(customer_order_window)
)

events_prepared = events_prepared.withColumn(
    "time_since_last_event_seconds",
    F.col("_event_ts_seconds") - F.col("_prior_event_ts_seconds"),
)

events_prepared = events_prepared.drop("_event_ts_seconds", "_prior_event_ts_seconds")

# COMMAND ----------

# MAGIC %md ## Assemble final Gold schema and add audit column

# COMMAND ----------

gold_events = events_prepared.select(
    # passthrough event fields
    "event_id",
    "customer_id",
    "event_timestamp",
    "event_type",
    "amount",
    "currency",
    "country",
    "channel",
    "device_id",
    "merchant_category",
    "authentication_status",
    # customer context
    "home_country",
    "normal_channel",
    "normal_device",
    "account_age_days",
    # computed features
    "prior_event_count_7d",
    "prior_avg_amount_90d",
    "amount_deviation_from_prior_avg",
    "is_new_device",
    "is_unusual_channel",
    "is_unusual_country",
    "prior_failed_login_count_24h",
    "time_since_last_event_seconds",
).withColumn("_computed_at", F.current_timestamp())

# COMMAND ----------

# MAGIC %md ## Row-count reconciliation
# MAGIC
# MAGIC Gold is a pure feature-enrichment transform, not a quarantine step — every
# MAGIC Silver event must appear exactly once. Unlike Silver's valid+rejects
# MAGIC reconciliation, there's no rejects path here: a row-count mismatch means a
# MAGIC bug (e.g. a join fan-out), not a data-quality failure, and should halt the
# MAGIC notebook.

# COMMAND ----------

gold_count = gold_events.count()
if gold_count != silver_events_count:
    raise ValueError(
        f"Row count mismatch: {silver_events_count} Silver events -> {gold_count} "
        f"Gold rows. Expected an exact 1:1 match. Investigate before writing."
    )

print(f"OK: {gold_count} Gold rows reconcile exactly with {silver_events_count} Silver events.")

# COMMAND ----------

# MAGIC %md ## Write to `ced.gold.customer_events_features`
# MAGIC
# MAGIC `mode("overwrite")`, consistent with Bronze and Silver conventions.

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.gold")

(
    gold_events.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.gold.customer_events_features")
)

print(f"Wrote {gold_count} rows to {CATALOG}.gold.customer_events_features")

# COMMAND ----------

# MAGIC %md ## Spot-check output

# COMMAND ----------

display(
    spark.table(f"{CATALOG}.gold.customer_events_features")
    .orderBy("customer_id", "event_timestamp")
    .limit(20)
)

# COMMAND ----------

# MAGIC %md ## Sanity checks
# MAGIC
# MAGIC - `is_new_device` should be `False` for the first event of most customers
# MAGIC   (their first device is very likely their declared `normal_device`, per the
# MAGIC   generator's design) and `True` only for a minority of later events.
# MAGIC - `time_since_last_event_seconds` should be `NULL` for exactly one row per
# MAGIC   customer (their first event) — 1,000 NULLs expected if all 1,000 customers
# MAGIC   have at least one event.
# MAGIC - `prior_avg_amount_90d` / `amount_deviation_from_prior_avg` should be `NULL`
# MAGIC   for all non-monetary event types, and non-NULL (after a customer's first
# MAGIC   monetary event) for monetary types.
# MAGIC - `prior_failed_login_count_24h` should be non-null on every row (it defaults
# MAGIC   to 0, not NULL, when there's no failed-login history in the window) and
# MAGIC   populated regardless of the current row's own event_type.

# COMMAND ----------

display(
    spark.table(f"{CATALOG}.gold.customer_events_features").agg(
        F.sum(F.col("time_since_last_event_seconds").isNull().cast("int")).alias(
            "null_time_since_last_event_count"
        ),
        F.sum(F.col("prior_failed_login_count_24h").isNull().cast("int")).alias(
            "null_prior_failed_login_count"
        ),
        F.sum(F.col("is_new_device").cast("int")).alias("new_device_true_count"),
        F.sum(F.col("is_unusual_channel").cast("int")).alias("unusual_channel_true_count"),
        F.sum(F.col("is_unusual_country").cast("int")).alias("unusual_country_true_count"),
    )
)

# COMMAND ----------

display(
    spark.table(f"{CATALOG}.gold.customer_events_features")
    .groupBy("event_type")
    .agg(
        F.count("*").alias("row_count"),
        F.sum(F.col("prior_avg_amount_90d").isNull().cast("int")).alias(
            "null_prior_avg_amount_count"
        ),
    )
    .orderBy("event_type")
)
