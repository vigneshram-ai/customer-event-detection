"""Tests for ingestion/upload_to_volume.py.

These tests mock the Databricks SDK client entirely -- no network calls, no
credentials required. CI has no Databricks credentials configured, so these
tests validate script logic (path construction, error handling) only. Live
upload behaviour is verified manually against the real workspace, not by CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ingestion.upload_to_volume import upload_file


def test_upload_file_missing_local_file(tmp_path: Path) -> None:
    client = MagicMock()
    missing = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        upload_file(client, missing, "/Volumes/ced/bronze/raw_uploads/does_not_exist.csv")

    client.files.upload.assert_not_called()


def test_upload_file_empty_local_file(tmp_path: Path) -> None:
    client = MagicMock()
    empty = tmp_path / "empty.csv"
    empty.write_text("")

    with pytest.raises(ValueError):
        upload_file(client, empty, "/Volumes/ced/bronze/raw_uploads/empty.csv")

    client.files.upload.assert_not_called()


def test_upload_file_calls_sdk_with_overwrite(tmp_path: Path) -> None:
    client = MagicMock()
    local_file = tmp_path / "customers.csv"
    local_file.write_text("customer_id,account_age_days\nCUST0000001,100\n")

    upload_file(client, local_file, "/Volumes/ced/bronze/raw_uploads/customers.csv")

    assert client.files.upload.call_count == 1
    call_args = client.files.upload.call_args
    assert call_args.args[0] == "/Volumes/ced/bronze/raw_uploads/customers.csv"
    assert call_args.kwargs["overwrite"] is True
