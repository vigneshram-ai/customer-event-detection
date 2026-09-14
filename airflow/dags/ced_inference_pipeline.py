"""
ced_inference_pipeline

Orchestrates the CED inference-side pipeline: Bronze -> Silver -> Gold ->
batch inference -> monitoring. This DAG never trains or promotes a model;
it always scores against whichever model version currently holds the
`champion` alias in the Unity Catalog model registry (ced.models).

Deliberately decoupled from ced_training_pipeline (see ADR-002 / M12 docs):
retraining is a separate, independently triggered decision, not something
that happens automatically on every inference run.

All tasks run via DatabricksSubmitRunOperator with the multi-task `tasks=[...]`
shape (no cluster spec), which is required for Databricks Free Edition
serverless compute -- DatabricksNotebookOperator does not support serverless
in the currently installed provider version, and the legacy single-task
notebook_task shorthand on DatabricksSubmitRunOperator requires a cluster.
Both were confirmed empirically during M12 design (see 99_databricks_serverless_test.py).
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
    dag_id="ced_inference_pipeline",
    description="Bronze -> Silver -> Gold -> batch inference -> monitoring (no training)",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ced", "inference"],
) as dag:
    bronze_ingestion = make_notebook_task(
        task_id="bronze_ingestion",
        notebook_filename="01.bronze_ingestion",
        run_name="ced_inference_bronze_ingestion",
    )

    silver_transformation = make_notebook_task(
        task_id="silver_transformation",
        notebook_filename="02.silver_transformation",
        run_name="ced_inference_silver_transformation",
    )

    gold_feature_engineering = make_notebook_task(
        task_id="gold_feature_engineering",
        notebook_filename="03.gold_feature_engineering",
        run_name="ced_inference_gold_feature_engineering",
    )

    batch_inference = make_notebook_task(
        task_id="batch_inference",
        notebook_filename="08.batch_inference",
        run_name="ced_inference_batch_inference",
    )

    monitoring = make_notebook_task(
        task_id="monitoring",
        notebook_filename="09.monitoring",
        run_name="ced_inference_monitoring",
    )

    (
        bronze_ingestion
        >> silver_transformation
        >> gold_feature_engineering
        >> batch_inference
        >> monitoring
    )
