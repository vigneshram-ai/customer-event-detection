# Databricks notebook source
# MAGIC %md
# MAGIC # Milestone 8 — ML Model Training (Logistic Regression + XGBoost)
# MAGIC
# MAGIC Trains two supervised models on the 8 Gold features against the
# MAGIC Milestone 3 ground-truth labels, and logs a metrics-only reference run
# MAGIC for the Milestone 7 baseline so all three are comparable in one MLflow
# MAGIC experiment.
# MAGIC
# MAGIC Per ADR-014:
# MAGIC - `ced.gold.customer_events_features` + `ced.training.ground_truth_labels`
# MAGIC   are joined **in-memory only**. The joined frame is never persisted to
# MAGIC   any catalog table.
# MAGIC - Only LogisticRegression and XGBoost are registered as real models, into
# MAGIC   a new `ced.models` schema — deliberately NOT `ced.training`, since
# MAGIC   registered models must be loadable by future batch inference, and
# MAGIC   `ced.training` is walled off from inference paths.
# MAGIC - The baseline is logged as a reference run (params/metrics only, no
# MAGIC   model artifact) since it isn't a fitted model — its numbers are the
# MAGIC   already-verified Milestone 7 results, not recomputed here.

# COMMAND ----------

# MAGIC %pip install xgboost

# COMMAND ----------

from databricks.sdk.runtime import dbutils

dbutils.library.restartPython()

# COMMAND ----------

import mlflow
import mlflow.sklearn
import mlflow.xgboost
import xgboost as xgb
from databricks.sdk.runtime import spark
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

CATALOG = "ced"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.models")

mlflow.set_registry_uri("databricks-uc")
EXPERIMENT_NAME = "/Shared/customer_event_detection_m8"
mlflow.set_experiment(EXPERIMENT_NAME)

FEATURE_COLS = [
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

# MAGIC %md ## Step 1: in-memory join (ADR-014 — never persisted to a table)

# COMMAND ----------

gold_df = spark.table(f"{CATALOG}.gold.customer_events_features")
labels_df = spark.table(f"{CATALOG}.training.ground_truth_labels")

joined = gold_df.join(
    labels_df.select("event_id", "is_anomaly", "anomaly_type"),
    on="event_id",
    how="left",
)
joined = joined.fillna({"is_anomaly": False})
# Rows with no matching label row are treated as normal, consistent with the
# left-join convention already used in evaluation/evaluate_baseline.py (M7).

gold_row_count = gold_df.count()
joined_row_count = joined.count()
print(f"Gold rows: {gold_row_count}, joined rows: {joined_row_count}")
assert gold_row_count == joined_row_count, (
    "Join changed row count vs. Gold input — investigate (possible fan-out) before proceeding."
)

pdf = joined.select(*FEATURE_COLS, "is_anomaly", "anomaly_type", "event_id").toPandas()
print(f"Collected {len(pdf)} rows to driver for training.")
print(f"Positive class (is_anomaly=True) count: {int(pdf['is_anomaly'].sum())}")

# COMMAND ----------

# MAGIC %md ## Step 2: stratified 70/30 split

# COMMAND ----------

# Stratify on anomaly_type (falling back to "normal") so small anomaly
# subtypes — e.g. the 128 channel_deviation rows — land in both splits.
pdf["strata"] = pdf["anomaly_type"].fillna("normal")

train_df, test_df = train_test_split(pdf, test_size=0.30, random_state=42, stratify=pdf["strata"])
print(f"Train: {len(train_df)}, Test: {len(test_df)}")
print("Train strata counts:")
print(train_df["strata"].value_counts())
print("Test strata counts:")
print(test_df["strata"].value_counts())

X_train = train_df[FEATURE_COLS].fillna(0)
y_train = train_df["is_anomaly"].astype(int)
X_test = test_df[FEATURE_COLS].fillna(0)
y_test = test_df["is_anomaly"].astype(int)

# COMMAND ----------

# MAGIC %md ## Step 3: log the Milestone 7 baseline as a reference run
# MAGIC (metrics only — no model artifact, since it isn't a fitted model)

# COMMAND ----------

with mlflow.start_run(run_name="baseline_rule_v1_reference"):
    mlflow.set_tag("model_type", "rule_based")
    mlflow.set_tag(
        "source",
        "Milestone 7, verified end-to-end against the full 27128-row dataset "
        "(see project-status.md / ADR-013) — not recomputed here.",
    )
    mlflow.log_param("scoring", "additive_point_scoring")
    mlflow.log_param("flag_threshold", 2)
    mlflow.log_metric("precision", 1.0000)
    mlflow.log_metric("recall", 0.7435)
    mlflow.log_metric("f1", 0.8529)
    mlflow.log_metric("recall_new_device", 1.0000)
    mlflow.log_metric("recall_geo_deviation", 1.0000)
    mlflow.log_metric("recall_amount_spike", 0.8070)
    mlflow.log_metric("recall_channel_deviation", 0.0)

print("Logged baseline reference run.")

# COMMAND ----------


def recall_by_type(test_df, y_pred):
    """Per-anomaly-type recall on the test split, same shape as M7's evaluation."""
    out = test_df.copy()
    out["pred"] = y_pred
    results = {}
    for atype in ["new_device", "geo_deviation", "amount_spike", "channel_deviation"]:
        subset = out[out["anomaly_type"] == atype]
        if len(subset) == 0:
            continue
        results[atype] = float(subset["pred"].mean())
    return results


# COMMAND ----------

# MAGIC %md ## Step 4: train + log Logistic Regression

# COMMAND ----------

with mlflow.start_run(run_name="logistic_regression"):
    mlflow.set_tag("model_type", "sklearn_logistic_regression")

    clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    mlflow.log_param("class_weight", "balanced")
    mlflow.log_param("max_iter", 1000)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    mlflow.log_metric("f1", f1)
    for atype, r in recall_by_type(test_df, y_pred).items():
        mlflow.log_metric(f"recall_{atype}", r)

    signature = mlflow.models.infer_signature(X_train, clf.predict(X_train))
    mlflow.sklearn.log_model(
        clf,
        "model",
        signature=signature,
        registered_model_name=f"{CATALOG}.models.logistic_regression_detector",
    )

    print(f"LogisticRegression — precision {precision:.4f}, recall {recall:.4f}, f1 {f1:.4f}")
    print(recall_by_type(test_df, y_pred))

# COMMAND ----------

# MAGIC %md ## Step 5: train + log XGBoost

# COMMAND ----------

with mlflow.start_run(run_name="xgboost"):
    mlflow.set_tag("model_type", "xgboost")

    scale_pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    clf_xgb = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss",
    )
    clf_xgb.fit(X_train, y_train)
    y_pred_xgb = clf_xgb.predict(X_test)

    precision = precision_score(y_test, y_pred_xgb)
    recall = recall_score(y_test, y_pred_xgb)
    f1 = f1_score(y_test, y_pred_xgb)

    mlflow.log_param("n_estimators", 200)
    mlflow.log_param("max_depth", 4)
    mlflow.log_param("learning_rate", 0.1)
    mlflow.log_param("scale_pos_weight", float(scale_pos_weight))
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    mlflow.log_metric("f1", f1)
    for atype, r in recall_by_type(test_df, y_pred_xgb).items():
        mlflow.log_metric(f"recall_{atype}", r)

    signature = mlflow.models.infer_signature(X_train, clf_xgb.predict(X_train))
    mlflow.xgboost.log_model(
        clf_xgb,
        "model",
        signature=signature,
        registered_model_name=f"{CATALOG}.models.xgboost_detector",
    )

    print(f"XGBoost — precision {precision:.4f}, recall {recall:.4f}, f1 {f1:.4f}")
    print(recall_by_type(test_df, y_pred_xgb))
