from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "airflow",
    "start_date": datetime(2025, 5, 1),
    "retries": 1,
}

with DAG(
    dag_id="dbt_pipeline",
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
    tags=["dbt"],
) as dag:

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            "cd /opt/airflow/statsbomb_dbt "
            "&& dbt deps --profiles-dir /opt/airflow/dbt_profiles "
            "&& dbt run --profiles-dir /opt/airflow/dbt_profiles"
        ),
    )

    dbt_run
