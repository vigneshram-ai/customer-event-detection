# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze Ingestion — Customer Event Detection
# MAGIC Reads raw CSVs landed in `ced.bronze.raw_uploads` (Milestone 4, Part A — see
# MAGIC `ingestion/upload_to_volume.py`) and writes them as Bronze Delta tables:
# MAGIC `ced.bronze.customers` and `ced.bronze.events`.
# MAGIC
# MAGIC ### Design principles
# MAGIC - Schema is **enforced** (explicit `StructType`), not inferred — but **not deeply
# MAGIC   validated**. Malformed rows are preserved, not rejected. Real data-quality rules
# MAGIC   (nulls, ranges, valid event types, referential integrity) belong to the Silver
# MAGIC   layer, not here.
# MAGIC - `event_timestamp` is kept as `StringType` in Bronze. Parsing it into a real
# MAGIC   `TimestampType` is a Silver-layer concern — Bronze stays a faithful,
# MAGIC   unopinionated copy of the ingested source.
# MAGIC - Audit columns (`_ingested_at`, `_source_file`) are added on write for
# MAGIC   traceability — a cheap, standard reliability pattern.
# MAGIC - Writes use `mode("overwrite")`: the synthetic datasets are full snapshot
# MAGIC   regenerations each run, not an incremental feed, so overwrite avoids
# MAGIC   duplicate accumulation across repeated test runs. Trade-off: this loses
# MAGIC   ingestion history compared to append-only. Acceptable for this project's
# MAGIC   scope; worth an ADR note if revisited.
# MAGIC - Header is validated against the expected column list before reading with
# MAGIC   an explicit schema — Spark maps schema columns **positionally**, not by
# MAGIC   name, so a reordered source column would otherwise land in the wrong
# MAGIC   field with no error.

# COMMAND ----------

from databricks.sdk.runtime import display, spark
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

CATALOG = "ced"
SCHEMA = "bronze"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_uploads"

# COMMAND ----------

CUSTOMERS_SCHEMA = StructType(
    [
        StructField("customer_id", StringType(), nullable=False),
        StructField("account_age_days", IntegerType(), nullable=False),
        StructField("home_country", StringType(), nullable=False),
        StructField("normal_channel", StringType(), nullable=False),
        StructField("normal_device", StringType(), nullable=False),
    ]
)

EVENTS_SCHEMA = StructType(
    [
        StructField("event_id", StringType(), nullable=False),
        StructField("customer_id", StringType(), nullable=False),
        StructField("event_timestamp", StringType(), nullable=False),  # parsed in Silver
        StructField("event_type", StringType(), nullable=False),
        StructField("amount", DoubleType(), nullable=True),
        StructField("currency", StringType(), nullable=True),
        StructField("country", StringType(), nullable=False),
        StructField("channel", StringType(), nullable=False),
        StructField("device_id", StringType(), nullable=False),
        StructField("merchant_category", StringType(), nullable=True),
        StructField("authentication_status", StringType(), nullable=True),
    ]
)

# COMMAND ----------


def _validate_header(csv_path: str, expected_columns: list[str]) -> None:
    """Fail fast if the CSV header doesn't match the expected column set.

    Spark's CSV reader maps an explicit schema POSITIONALLY when a header row
    is present but the schema is user-supplied -- it does not validate column
    names against the schema. Without this check, a reordered or renamed
    source column would silently land in the wrong Bronze column instead of
    raising an error.
    """
    header_line = spark.read.text(csv_path).first()[0]
    actual_columns = [c.strip() for c in header_line.split(",")]
    if actual_columns != expected_columns:
        raise ValueError(
            f"Header mismatch in {csv_path}.\n"
            f"Expected: {expected_columns}\n"
            f"Actual:   {actual_columns}"
        )


# COMMAND ----------


def ingest_to_bronze(source_filename: str, schema: StructType, table_name: str) -> None:
    csv_path = f"{VOLUME_PATH}/{source_filename}"
    expected_columns = [f.name for f in schema.fields]

    _validate_header(csv_path, expected_columns)

    df = spark.read.option("header", "true").schema(schema).csv(csv_path)

    row_count = df.count()
    if row_count == 0:
        raise ValueError(
            f"{csv_path} produced zero rows after read -- refusing to write Bronze table."
        )

    df_with_audit = df.withColumn("_ingested_at", F.current_timestamp()).withColumn(
        "_source_file", F.lit(source_filename)
    )

    full_table_name = f"{CATALOG}.{SCHEMA}.{table_name}"
    df_with_audit.write.mode("overwrite").saveAsTable(full_table_name)

    written_count = spark.table(full_table_name).count()
    if written_count != row_count:
        raise ValueError(
            f"Row count mismatch after writing {full_table_name}: "
            f"read {row_count} rows, table has {written_count} rows."
        )

    print(f"OK: {full_table_name} -- {written_count:,} rows")


# COMMAND ----------

ingest_to_bronze("customers.csv", CUSTOMERS_SCHEMA, "customers")

# COMMAND ----------

ingest_to_bronze("events.csv", EVENTS_SCHEMA, "events")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification queries
# MAGIC Run the cells below after the ingestion cells above complete successfully.

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.customers"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.events"))

# COMMAND ----------

display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.events LIMIT 5"))
