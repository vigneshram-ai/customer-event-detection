"""Evaluate the Milestone 7 baseline rule-based detector against the
Milestone 3 synthetic ground-truth anomaly labels.

Downloads ced.gold.baseline_detections (exported to a Unity Catalog volume
by notebooks/baseline_detector.py) via databricks-sdk, joins it locally
against data/raw/events_ground_truth.csv on event_id, and reports
precision/recall/F1/false-positive rate for detection_flag.

Local, one-off script — not part of the Databricks pipeline. Ground truth
is synthetic-only and deliberately never uploaded to the warehouse (ADR-010).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

VOLUME_PATH = "/Volumes/ced/gold/exports/baseline_detections.csv"
LOCAL_DETECTIONS_PATH = Path("data/raw/baseline_detections.csv")
GROUND_TRUTH_PATH = Path("data/raw/events_ground_truth.csv")


def download_detections() -> Path:
    load_dotenv()
    client = WorkspaceClient()
    response = client.files.download(VOLUME_PATH)
    contents = response.contents.read()
    LOCAL_DETECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_DETECTIONS_PATH.write_bytes(contents)
    print(f"Downloaded {VOLUME_PATH} -> {LOCAL_DETECTIONS_PATH} ({len(contents)} bytes)")
    return LOCAL_DETECTIONS_PATH


def load_and_join() -> pd.DataFrame:
    detections = pd.read_csv(LOCAL_DETECTIONS_PATH)
    ground_truth = pd.read_csv(GROUND_TRUTH_PATH)

    if len(detections) != len(ground_truth):
        print(
            f"WARNING: row count mismatch before join — "
            f"detections={len(detections)}, ground_truth={len(ground_truth)}"
        )

    merged = detections.merge(ground_truth, on="event_id", how="inner", validate="one_to_one")

    if len(merged) != len(detections):
        print(
            f"WARNING: join dropped rows — {len(detections)} detections, "
            f"{len(merged)} matched to ground truth"
        )

    return merged


def compute_metrics(df: pd.DataFrame) -> dict:
    y_true = df["is_synthetic_anomaly"].astype(bool)
    y_pred = df["detection_flag"].astype(bool)

    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    tn = int((~y_true & ~y_pred).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fpr,
    }


def breakdown_by_anomaly_type(df: pd.DataFrame) -> pd.DataFrame:
    anomalies = df[df["is_synthetic_anomaly"]]
    return (
        anomalies.groupby("anomaly_type")
        .agg(count=("event_id", "count"), caught=("detection_flag", "sum"))
        .assign(recall=lambda d: d["caught"] / d["count"])
        .sort_values("count", ascending=False)
    )


def main() -> None:
    download_detections()
    merged = load_and_join()
    metrics = compute_metrics(merged)

    print("\n=== Overall metrics ===")
    for key, value in metrics.items():
        print(f"{key}: {value:.4f}" if isinstance(value, float) else f"{key}: {value}")

    print("\n=== Recall by anomaly_type ===")
    print(breakdown_by_anomaly_type(merged).to_string())


if __name__ == "__main__":
    main()
