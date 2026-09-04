"""
Uploads the Milestone 3 ground-truth sidecar file to a Databricks Unity Catalog
volume, as a CSV, for later loading into ced.training.ground_truth_labels.

This is a NEW, additive script. It does NOT modify ingestion/upload_to_volume.py,
which continues to deliberately exclude ground truth from Bronze uploads (ADR-010).
Ground truth here goes only to ced.training, a schema isolated from bronze/silver/gold
and never read by inference paths, per ADR-014.
"""

import io
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

load_dotenv()

VOLUME_PATH = "/Volumes/ced/training/raw_labels/events_ground_truth.csv"
LOCAL_PATH = Path("data/raw/events_ground_truth.csv")


def upload_ground_truth() -> None:
    if not LOCAL_PATH.exists():
        print(f"ERROR: {LOCAL_PATH} not found. Run event_generator.py first.")
        sys.exit(1)

    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    if not host or not token:
        print("ERROR: DATABRICKS_HOST / DATABRICKS_TOKEN not set (.env missing?).")
        sys.exit(1)

    w = WorkspaceClient(host=host, token=token)

    with open(LOCAL_PATH, "rb") as f:
        contents = f.read()

    print(f"Uploading {LOCAL_PATH} ({len(contents)} bytes) -> {VOLUME_PATH}")
    w.files.upload(VOLUME_PATH, io.BytesIO(contents), overwrite=True)
    print("OK: upload complete.")


if __name__ == "__main__":
    upload_ground_truth()
