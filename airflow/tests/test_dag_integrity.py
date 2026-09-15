"""
DAG integrity tests for the CED Airflow DAGs.

Deliberately NOT under tests/ (see pyproject.toml testpaths=["tests"]):
apache-airflow is not a project dependency (ADR-018), so this file is only
ever collected by the CI job that installs Airflow into its own throwaway
environment (.github/workflows/ci.yml -> dag-integrity job), never by
`uv run pytest`.

This uses airflow.models.DagBag directly rather than spinning up a full
Airflow metadata database -- confirmed empirically (Milestone 14 design
step) that DagBag parsing requires no AIRFLOW_HOME/db init, only the dag
folder itself. Airflow 3.x also dropped the `include_examples` kwarg that
appears in a lot of older DagBag examples online -- worth documenting since
it silently breaks the naive version of this test.
"""

from pathlib import Path

from airflow.models import DagBag

DAG_FOLDER = Path(__file__).resolve().parents[1] / "dags"

EXPECTED_DAGS = {
    "ced_inference_pipeline": [
        "bronze_ingestion",
        "silver_transformation",
        "gold_feature_engineering",
        "batch_inference",
        "monitoring",
    ],
    "ced_training_pipeline": [
        "train_model",
        "validate_and_promote_model",
    ],
}


def _load_dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAG_FOLDER))


def test_no_import_errors():
    bag = _load_dagbag()
    assert bag.import_errors == {}, f"DAG import errors: {bag.import_errors}"


def test_expected_dags_present():
    bag = _load_dagbag()
    assert set(bag.dags.keys()) == set(EXPECTED_DAGS.keys()), (
        f"Expected DAGs {set(EXPECTED_DAGS.keys())}, found {set(bag.dags.keys())}"
    )


def test_expected_tasks_present():
    bag = _load_dagbag()
    for dag_id, expected_task_ids in EXPECTED_DAGS.items():
        dag = bag.dags[dag_id]
        actual_task_ids = [t.task_id for t in dag.tasks]
        assert actual_task_ids == expected_task_ids, (
            f"{dag_id}: expected task order {expected_task_ids}, got {actual_task_ids}"
        )


def test_dags_are_not_scheduled():
    # Both DAGs are deliberately schedule=None (ADR-018: no persistent
    # WSL2 scheduler survives a laptop shutdown). schedule=None resolves to
    # a NullTimetable at parse time (confirmed empirically against Airflow
    # 3.3.1 -- note `dag.schedule_interval` no longer exists on Airflow 3.x
    # DAG objects, unlike most Airflow 2.x-era examples). This test exists
    # so that re-enabling a schedule is a conscious, reviewed change, not
    # an accidental one.
    bag = _load_dagbag()
    for dag_id in EXPECTED_DAGS:
        timetable_type = type(bag.dags[dag_id].timetable).__name__
        assert timetable_type == "NullTimetable", (
            f"{dag_id} has timetable {timetable_type}, expected NullTimetable "
            "(schedule=None); confirm this is intentional (ADR-018)"
        )


def test_default_retries_configured():
    bag = _load_dagbag()
    for dag_id in EXPECTED_DAGS:
        dag = bag.dags[dag_id]
        assert dag.default_args.get("retries", 0) >= 1, (
            f"{dag_id} has no retry configured in default_args"
        )
