"""
training/train_model_job.py

Script-task adaptation of notebooks/train_model.py (Milestone 8), for
execution as a Databricks Job `spark_python_task` on Container-Services-backed
classic/dedicated compute, instead of as a notebook on serverless compute.

STATUS: DESIGNED ONLY — adapted from the real, verified M8 notebook source,
but never executed in this form. Running this as a real Databricks Job
requires classic/dedicated compute, which Databricks Free Edition (this
project's only workspace) does not offer. See
docs/adr/ADR-020-docker-container-services.md.

WHAT CHANGED FROM notebooks/train_model.py, AND WHY
----------------------------------------------------
1. The `%pip install xgboost` + `dbutils.library.restartPython()` notebook
   cell is REMOVED. It existed to install xgboost at notebook runtime and
   restart the interpreter to pick it up. The train-job Docker image
   (docker/train-job/Dockerfile) already has xgboost==3.4.1 baked in at
   build time — that's the entire point of the "golden container" pattern.
   The Dockerfile now does this job instead of the notebook.

2. `from databricks.sdk.runtime import spark` is REPLACED with
   `SparkSession.builder.getOrCreate()`. The `databricks.sdk.runtime`
   magic-import pattern is documented for notebook execution specifically.
   For a plain Python script run as a Databricks Job `spark_python_task`
   (not a notebook task), the standard, documented way to get a working,
   Unity-Catalog-aware Spark session is to call
   SparkSession.builder.getOrCreate() directly, which on Databricks compute
   returns the cluster's already-configured active session. `dbutils` is
   not used anywhere else in the original script (only for the restart
   above), so it is dropped entirely rather than reconstructed via
   `pyspark.dbutils.DBUtils`.

EVERYTHING ELSE below — feature columns, the in-memory join and its ADR-014
row-count assertion, the stratified split, the baseline reference run, both
training runs, and the registered model names — is unchanged from the real,
verified M8 notebook.
"""

import mlflow
import mlflow.sklearn
import mlflow.xgboost
import xgboost as xgb
from pyspark.sql import SparkSession
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

spark = SparkSession.builder.getOrCreate()

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


def main():
    # Step 1: in-memory join (ADR-014 — never persisted to a table)
    gold_df = spark.table(f"{CATALOG}.gold.customer_events_features")
    labels_df = spark.table(f"{CATALOG}.training.ground_truth_labels")

    joined = gold_df.join(
        labels_df.select("event_id", "is_anomaly", "anomaly_type"),
        on="event_id",
        how="left",
    )
    joined = joined.fillna({"is_anomaly": False})
    # Rows with no matching label row are treated as normal, consistent with
    # the left-join convention already used in evaluation/evaluate_baseline.py (M7).

    gold_row_count = gold_df.count()
    joined_row_count = joined.count()
    print(f"Gold rows: {gold_row_count}, joined rows: {joined_row_count}")
    assert gold_row_count == joined_row_count, (
        "Join changed row count vs. Gold input — investigate (possible fan-out) before proceeding."
    )

    pdf = joined.select(*FEATURE_COLS, "is_anomaly", "anomaly_type", "event_id").toPandas()
    print(f"Collected {len(pdf)} rows to driver for training.")
    print(f"Positive class (is_anomaly=True) count: {int(pdf['is_anomaly'].sum())}")

    # Step 2: stratified 70/30 split
    # Stratify on anomaly_type (falling back to "normal") so small anomaly
    # subtypes — e.g. the 128 channel_deviation rows — land in both splits.
    pdf["strata"] = pdf["anomaly_type"].fillna("normal")

    train_df, test_df = train_test_split(
        pdf, test_size=0.30, random_state=42, stratify=pdf["strata"]
    )
    print(f"Train: {len(train_df)}, Test: {len(test_df)}")
    print("Train strata counts:")
    print(train_df["strata"].value_counts())
    print("Test strata counts:")
    print(test_df["strata"].value_counts())

    X_train = train_df[FEATURE_COLS].fillna(0)
    y_train = train_df["is_anomaly"].astype(int)
    X_test = test_df[FEATURE_COLS].fillna(0)
    y_test = test_df["is_anomaly"].astype(int)

    # Step 3: log the Milestone 7 baseline as a reference run
    # (metrics only — no model artifact, since it isn't a fitted model)
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

    # Step 4: train + log Logistic Regression
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

    # Step 5: train + log XGBoost
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


if __name__ == "__main__":
    main()
