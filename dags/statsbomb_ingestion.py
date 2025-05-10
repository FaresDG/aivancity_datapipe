import json
import logging
import requests
from datetime import timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.utils.dates import days_ago
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

# URL de base pour les données StatsBomb (branche main)
BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Nom du bucket MinIO (défini dans une Variable Airflow si besoin)
BUCKET = Variable.get("STATSBOMB_BUCKET", default_var="statsbomb")

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def fetch_and_upload(key: str, url: str):
    """
    Télécharge l'URL et upload son contenu brut dans MinIO/S3 sous la clé spécifiée.
    """
    logging.info(f"Downloading {url}")
    resp = requests.get(url)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        logging.warning(f"{url} introuvable ({resp.status_code}), j’ignore.")
        return

    content = resp.content
    hook = S3Hook(aws_conn_id="minio_default")
    hook.load_bytes(
        bytes_data=content,
        key=key,
        bucket_name=BUCKET,
        replace=True,
    )
    logging.info(f"Uploaded to s3://{BUCKET}/{key}")


def ingest_competitions():
    """Télécharge competitions.json et l'upload dans MinIO."""
    fetch_and_upload(key="competitions.json", url=f"{BASE_URL}/competitions.json")


def ingest_matches():
    """
    Pour chaque compétition/saison, tente de télécharger matches/{cid}/{sid}.json puis upload.
    """
    # Récupère la liste des compétitions
    r = requests.get(f"{BASE_URL}/competitions.json")
    r.raise_for_status()
    competitions = r.json()

    for comp in competitions:
        cid = comp["competition_id"]
        sid = comp["season_id"]
        url = f"{BASE_URL}/matches/{cid}/{sid}.json"
        key = f"matches/{cid}/{sid}.json"
        fetch_and_upload(key=key, url=url)


def ingest_events_and_lineups():
    """
    Pour chaque match téléchargé, télécharge les events et lineups correspondants.
    """
    # On relit la liste des compétitions
    r = requests.get(f"{BASE_URL}/competitions.json")
    r.raise_for_status()
    competitions = r.json()

    for comp in competitions:
        cid = comp["competition_id"]
        sid = comp["season_id"]

        # Tente de récupérer la liste des matches
        matches_url = f"{BASE_URL}/matches/{cid}/{sid}.json"
        resp = requests.get(matches_url)
        if resp.status_code != 200:
            logging.warning(f"{matches_url} introuvable, j’ignore cette comp/saison.")
            continue

        matches = resp.json()
        for m in matches:
            mid = m["match_id"]

            # EVENTS
            ev_url = f"{BASE_URL}/events/{mid}.json"
            ev_key = f"events/{mid}.json"
            fetch_and_upload(key=ev_key, url=ev_url)

            # LINEUPS
            lu_url = f"{BASE_URL}/lineups/{mid}.json"
            lu_key = f"lineups/{mid}.json"
            fetch_and_upload(key=lu_key, url=lu_url)


with DAG(
    dag_id="statsbomb_full_ingestion",
    default_args=default_args,
    description="Ingestion complète des données StatsBomb vers MinIO",
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["statsbomb", "ingestion"],
) as dag:

    t1 = PythonOperator(
        task_id="ingest_competitions",
        python_callable=ingest_competitions,
    )

    t2 = PythonOperator(
        task_id="ingest_matches",
        python_callable=ingest_matches,
    )

    t3 = PythonOperator(
        task_id="ingest_events_and_lineups",
        python_callable=ingest_events_and_lineups,
    )

    t1 >> t2 >> t3
