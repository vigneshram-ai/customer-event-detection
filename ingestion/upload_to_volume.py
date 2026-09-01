"""Upload local synthetic data CSVs to a Databricks Unity Catalog volume.

This is the first step of Bronze-layer ingestion: it moves customers.csv and
events.csv (Milestone 2 / Milestone 3 outputs) from local disk into the
CED.bronze.raw_uploads Unity Catalog volume, where a Databricks-side PySpark
job then reads them and writes Bronze Delta tables (separate step).

Deliberately excludes events_ground_truth.csv: the ground-truth sidecar is an
evaluation artifact, not part of the raw ingestion source, so it does not
belong in the Bronze landing zone -- same reasoning as Milestone 3's decision
to keep it out of events.csv.

Auth: reads DATABRICKS_HOST / DATABRICKS_TOKEN from the environment (see
.env, loaded via python-dotenv). Credentials are never passed as arguments
or hardcoded.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv


def upload_file(client: WorkspaceClient, local_path: Path, volume_path: str) -> None:
    """Upload a single local file to UC volume path"""
    if not local_path.exists():
        raise FileNotFoundError(f"Local file not found : {local_path}")
    if local_path.stat().st_size == 0:
        raise ValueError(f"Local file is empty: {local_path}")

    with local_path.open("rb") as f:
        client.files.upload(volume_path, f, overwrite=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload synthetic customers/events CSVs to a Databricks UC volume."
    )
    parser.add_argument("--customers-file", type=Path, default=Path("data/raw/customers.csv"))
    parser.add_argument("--events-file", type=Path, default=Path("data/raw/events.csv"))
    parser.add_argument("--volume-path", type=str, default="/Volumes/ced/bronze/raw_uploads")
    args = parser.parse_args()

    load_dotenv()
    client = WorkspaceClient()

    targets = {
        args.customers_file: f"{args.volume_path}/customers.csv",
        args.events_file: f"{args.volume_path}/events.csv",
    }

    for local_path, remote_path in targets.items():
        print(f"Uploading {local_path} -> {remote_path}")
        upload_file(client, local_path, remote_path)
        print(f"  OK ({local_path.stat().st_size:,} bytes)")

    print("Upload complete.")


if __name__ == "__main__":
    main()
