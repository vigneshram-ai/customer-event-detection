"""Milestone 1 smoke test DAG.

Purpose: verify the Airflow environment (scheduler, DAG processor, API
server, LocalExecutor) is wired up correctly. Contains no pipeline logic.
Will be removed once Milestone 12 introduces the real orchestration DAG.
"""

from __future__ import annotations

import platform

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="00_environment_smoke_test",
    schedule=None,  # manual trigger only — this is not a real scheduled job
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["milestone-1", "smoke-test"],
)
def environment_smoke_test():
    @task
    def check_environment():
        print(f"Python version in container: {platform.python_version()}")
        print("Airflow LocalExecutor environment is working.")
        return "ok"

    check_environment()


environment_smoke_test()