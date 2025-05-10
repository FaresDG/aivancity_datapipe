from datetime import datetime
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2025, 5, 1),
}

with DAG(
    dag_id='dbt_pipeline',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:

    dbt_run = DockerOperator(
        task_id='dbt_run',
        image='dbt:1.9.4',  # ou le nom de ton image dbt si tu as personnalisé
        api_version='auto',
        auto_remove=True,
        docker_url='unix://var/run/docker.sock',
        network_mode='bridge',
        mounts=[
            Mount(source='/var/run/docker.sock', target='/var/run/docker.sock', type='bind'),
            Mount(source='/opt/airflow/statsbomb_dbt', target='/usr/app', type='bind'),
            Mount(source='/opt/airflow/dbt_profiles', target='/root/.dbt', type='bind'),
        ],
        working_dir='/usr/app',
        command="dbt run --profiles-dir /root/.dbt",
    )

    dbt_run
