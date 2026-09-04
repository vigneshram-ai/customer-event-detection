from unittest.mock import MagicMock, patch

import pytest

from training import upload_ground_truth


def test_exits_when_local_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_ground_truth, "LOCAL_PATH", tmp_path / "missing.csv")
    with pytest.raises(SystemExit):
        upload_ground_truth.upload_ground_truth()


def test_exits_when_env_vars_missing(tmp_path, monkeypatch):
    fake_csv = tmp_path / "events_ground_truth.csv"
    fake_csv.write_text("event_id,anomaly_type\n1,new_device\n")
    monkeypatch.setattr(upload_ground_truth, "LOCAL_PATH", fake_csv)
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        upload_ground_truth.upload_ground_truth()


def test_uploads_with_correct_volume_path(tmp_path, monkeypatch):
    fake_csv = tmp_path / "events_ground_truth.csv"
    fake_csv.write_text("event_id,anomaly_type\n1,new_device\n")
    monkeypatch.setattr(upload_ground_truth, "LOCAL_PATH", fake_csv)
    monkeypatch.setenv("DATABRICKS_HOST", "https://fake-host")
    monkeypatch.setenv("DATABRICKS_TOKEN", "fake-token")

    mock_client = MagicMock()
    with patch.object(upload_ground_truth, "WorkspaceClient", return_value=mock_client):
        upload_ground_truth.upload_ground_truth()

    mock_client.files.upload.assert_called_once()
    args, _kwargs = mock_client.files.upload.call_args
    assert args[0] == upload_ground_truth.VOLUME_PATH
