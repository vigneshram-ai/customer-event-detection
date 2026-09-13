# Databricks notebook source
# MAGIC %pip install evidently

# COMMAND ----------
from databricks.sdk.runtime import dbutils

dbutils.library.restartPython()

# COMMAND ----------
import json
import uuid
from datetime import UTC, datetime

import pandas as pd
from databricks.sdk.runtime import dbutils, displayHTML, spark
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset, DataSummaryPreset

# COMMAND ----------
# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REFERENCE_TABLE = "ced.gold.customer_events_features"
CURRENT_TABLE = "ced.inference.detection_results"
MONITORING_TABLE = "ced.monitoring.batch_quality_report"

NUMERIC_FEATURES = [
    "prior_event_count_7d",
    "prior_avg_amount_90d",
    "amount_deviation_from_prior_avg",
    "prior_failed_login_count_24h",
    "time_since_last_event_seconds",
]
BINARY_FEATURES = [
    "is_new_device",
    "is_unusual_channel",
    "is_unusual_country",
]
FEATURE_COLUMNS = NUMERIC_FEATURES + BINARY_FEATURES

RUN_ID = str(uuid.uuid4())
SCORED_AT = datetime.now(UTC)

print(f"Monitoring run_id: {RUN_ID}")
print(f"Scored at (UTC): {SCORED_AT.isoformat()}")

# COMMAND ----------
# ---------------------------------------------------------------------------
# Load reference (training-time population) and current (batch under monitoring)
# ---------------------------------------------------------------------------
reference_pdf = spark.table(REFERENCE_TABLE).select(FEATURE_COLUMNS).toPandas()

current_pdf = (
    spark.table(CURRENT_TABLE)
    .select(FEATURE_COLUMNS + ["detection_score", "detection_flag"])
    .toPandas()
)

print(f"Reference rows ({REFERENCE_TABLE}): {len(reference_pdf)}")
print(f"Current rows ({CURRENT_TABLE}): {len(current_pdf)}")

# COMMAND ----------
# ---------------------------------------------------------------------------
# Train/serve parity, corrected: it turns out ced.inference.detection_results
# stores RAW (non-imputed) feature values, not the post-fillna(0) values fed
# to the model. Milestone 10's fillna(0) fix was applied to the transient
# scoring matrix only (hence detection_score/detection_flag are correct) —
# it was never propagated back into the persisted output columns. This
# contradicts what ADR-016/current-context.md previously claimed and needs
# a documentation correction at M11 close (see conversation). For this
# notebook, both reference and current need the identical imputation
# applied here, not just reference, since both sides are raw.
# ---------------------------------------------------------------------------
reference_pdf[FEATURE_COLUMNS] = reference_pdf[FEATURE_COLUMNS].fillna(0)
current_pdf[FEATURE_COLUMNS] = current_pdf[FEATURE_COLUMNS].fillna(0)

# Fail-fast pipeline guard rails (contract checks, not monitoring metrics —
# Evidently owns the actual metrics below).
null_check = current_pdf[FEATURE_COLUMNS + ["detection_score", "detection_flag"]].isnull().sum()
assert null_check.sum() == 0, f"Unexpected NULLs remain after imputation:\n{null_check}"
assert len(current_pdf) > 0, "Current batch is empty — nothing to monitor."

# COMMAND ----------
# ---------------------------------------------------------------------------
# Data definitions — explicit column typing so binary 0/1 flags are treated
# as categorical, not numerical. Reference and current-for-drift datasets
# must share an identical definition per Evidently's requirements.
# ---------------------------------------------------------------------------
feature_definition = DataDefinition(
    numerical_columns=NUMERIC_FEATURES,
    categorical_columns=BINARY_FEATURES,
)

reference_dataset = Dataset.from_pandas(
    reference_pdf[FEATURE_COLUMNS], data_definition=feature_definition
)
current_features_dataset = Dataset.from_pandas(
    current_pdf[FEATURE_COLUMNS], data_definition=feature_definition
)

full_definition = DataDefinition(
    numerical_columns=NUMERIC_FEATURES + ["detection_score"],
    categorical_columns=BINARY_FEATURES + ["detection_flag"],
)
current_full_dataset = Dataset.from_pandas(
    current_pdf[FEATURE_COLUMNS + ["detection_score", "detection_flag"]],
    data_definition=full_definition,
)

# COMMAND ----------
# ---------------------------------------------------------------------------
# Data Drift Report — current batch vs. reference (training) population.
# Method left as Evidently's default (auto-selected per column: e.g.
# Wasserstein distance for numerical, Jensen-Shannon distance for
# categorical). Each test has its own calibrated threshold and rolls up
# into a per-column Drifted/Not-Drifted boolean, so cross-feature
# comparability doesn't require forcing a single metric like PSI — that
# was the original (incorrect) justification for overriding the default;
# corrected after review. PSI remains the standard drift metric in
# banking/credit-risk monitoring specifically, worth knowing as domain
# context, but auto-select is what's actually running here.
# ---------------------------------------------------------------------------
drift_report = Report([DataDriftPreset()], include_tests="True")
drift_eval = drift_report.run(current_features_dataset, reference_dataset)

drift_html_path = f"/tmp/evidently_drift_{RUN_ID}.html"
drift_eval.save_html(drift_html_path)
with open(drift_html_path, encoding="utf-8") as f:
    displayHTML(f.read())

# COMMAND ----------
# ---------------------------------------------------------------------------
# Data Summary Report — single-dataset quality/summary stats on the current
# batch (nulls, ranges, distributions), including detection_score/
# detection_flag as descriptive snapshot stats. No reference comparison for
# these two columns — no prior scored batch exists (this is the first and
# only inference run), so this is a snapshot, not a drift check.
# ---------------------------------------------------------------------------
summary_report = Report([DataSummaryPreset()], include_tests="True")
summary_eval = summary_report.run(current_full_dataset, None)

summary_html_path = f"/tmp/evidently_summary_{RUN_ID}.html"
summary_eval.save_html(summary_html_path)
with open(summary_html_path, encoding="utf-8") as f:
    displayHTML(f.read())


# COMMAND ----------
# ---------------------------------------------------------------------------
# Flatten Evidently's output into the persisted table. Defensive: if the
# dict shape doesn't match what's expected, fall back to storing the raw
# JSON for that report rather than failing the run.
# ---------------------------------------------------------------------------
def flatten_evidently_report(eval_result, category: str) -> list[dict]:
    try:
        d = eval_result.dict()
        metrics = d.get("metrics", [])
        tests = d.get("tests", [])

        # Each metric has an opaque "id" (hash) and a human-readable
        # "metric_name" (e.g. "ValueDrift(column=..., method=..., threshold=...)").
        # Tests link back to metrics via test["metric_config"]["metric_id"],
        # which matches the metric's "id". A test's "description" already
        # states the actual measured value against its threshold in plain
        # language, so it doubles as our persisted threshold/context field.
        status_by_metric_id = {}
        description_by_metric_id = {}
        for t in tests:
            metric_id = t.get("metric_config", {}).get("metric_id")
            if metric_id:
                status_by_metric_id[metric_id] = t.get("status", "UNKNOWN")
                description_by_metric_id[metric_id] = t.get("description", "")

        rows = []
        for m in metrics:
            metric_id = m.get("id")
            metric_name = m.get("metric_name") or str(metric_id)
            value = m.get("value")
            status = status_by_metric_id.get(metric_id, "NO_TEST")
            threshold = description_by_metric_id.get(metric_id, "evidently_default")
            rows.append(
                {
                    "metric_category": category,
                    "metric_name": metric_name,
                    "value": str(value),
                    "threshold": threshold,
                    "status": str(status),
                }
            )
        if rows:
            return rows
        raise ValueError("Parsed 0 metric rows from report.dict()")
    except Exception as e:  # noqa: BLE001 - deliberate broad catch, see design note above
        print(f"[monitoring] Structured extraction failed for '{category}': {e}")
        print(
            "[monitoring] Falling back to raw JSON row. Paste this output back "
            "so the extraction logic can be corrected."
        )
        return [
            {
                "metric_category": category,
                "metric_name": "raw_report_json",
                "value": json.dumps(eval_result.dict(), default=str)[:8000],
                "threshold": "n/a",
                "status": "EXTRACTION_FAILED",
            }
        ]


drift_rows = flatten_evidently_report(drift_eval, "drift")
summary_rows = flatten_evidently_report(summary_eval, "data_quality_and_summary")

# COMMAND ----------
# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------
all_rows = drift_rows + summary_rows
summary_pdf = pd.DataFrame(all_rows)
summary_pdf["run_id"] = RUN_ID
summary_pdf["scored_at"] = SCORED_AT

summary_df = spark.createDataFrame(summary_pdf)

(summary_df.write.format("delta").mode("append").saveAsTable(MONITORING_TABLE))

print(f"Wrote {len(all_rows)} metric rows to {MONITORING_TABLE} (run_id={RUN_ID})")
print(f"Drift metrics: {len(drift_rows)}  |  Summary/quality metrics: {len(summary_rows)}")

fail_like = [r for r in all_rows if r["status"] not in ("TestStatus.SUCCESS", "NO_TEST")]
print(f"Rows with a non-passing/unexpected status: {len(fail_like)}")
for r in fail_like:
    print(f"  [{r['metric_category']}] {r['metric_name']} = {r['value']}  status={r['status']}")
