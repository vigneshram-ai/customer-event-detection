"""
ced_training_pipeline

Orchestrates the CED training/validation/promotion pipeline: train_model ->
validate_and_promote_model. Deliberately NOT chained to ced_inference_pipeline
and NOT scheduled by default -- retraining is a manually triggered, reviewed
decision (new data, scheduled cadence, or a monitoring-triggered signal), not
something that fires on every inference run.

Connection point to ced_inference_pipeline is the Unity Catalog model
registry alias (`champion`) in ced.models, not a direct Airflow dependency:
this DAG updates which model version holds `champion`; ced_inference_pipeline
always reads whichever version currently holds it. See ADR-002 / M12 docs.

Assumes ced.gold.customer_events_features is already current -- this DAG
does not re-run Bronze/Silver/Gold itself. Training against a deliberately
chosen data snapshot (rather than implicitly depending on the inference
DAG's own schedule) is a conscious M12 design decision -- confirm with the
project owner before changing.

Tasks use the DatabricksSubmitRunOperator `tasks=[...]` multi-task shape,
required for Databricks Free Edition serverless compute (see
ced_inference_pipeline.py docstring / 99_databricks_serverless_test.py for
why DatabricksNotebookOperator and the legacy notebook_task shorthand don't
work here).
"""

from datetime import datetime, timedelta

from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator

from airflow import DAG

WORKSPACE_BASE = "/Workspace/Users/vigneshram230693@gmail.com/CED"

DEFAULT_ARGS = {
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def make_notebook_task(
    task_id: str, notebook_filename: str, run_name: str
) -> DatabricksSubmitRunOperator:
    """Build a single-notebook DatabricksSubmitRunOperator using the
    multi-task `tasks=[...]` shape required for serverless compute."""
    return DatabricksSubmitRunOperator(
        task_id=task_id,
        databricks_conn_id="databricks_default",
        run_name=run_name,
        tasks=[
            {
                "task_key": task_id,
                "notebook_task": {
                    "notebook_path": f"{WORKSPACE_BASE}/{notebook_filename}",
                },
            }
        ],
    )


with DAG(
    dag_id="ced_training_pipeline",
    description="train_model -> validate_and_promote_model (manually triggered)",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ced", "training"],
) as dag:
    train_model = make_notebook_task(
        task_id="train_model",
        notebook_filename="06.train_model",
        run_name="ced_training_train_model",
    )

    validate_and_promote_model = make_notebook_task(
        task_id="validate_and_promote_model",
        notebook_filename="07.validate_and_promote_model",
        run_name="ced_training_validate_and_promote_model",
    )

    train_model >> validate_and_promote_model
