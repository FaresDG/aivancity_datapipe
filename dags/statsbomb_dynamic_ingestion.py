import json
import logging
import time
import requests
from requests.exceptions import ConnectionError, Timeout
from typing import List
from datetime import timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
BUCKET = "statsbomb"
CHUNK_SIZE = 100  # nombre de match_ids par tâche

def robust_get(url: str, retries: int = 5, backoff: int = 5, timeout: int = 30) -> requests.Response:
    """
    Téléchargement robuste avec retries et backoff.
    """
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, timeout=timeout)
        except (ConnectionError, Timeout) as e:
            logging.warning(f"GET {url} failed (try {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(backoff)
            else:
                raise

@dag(
    dag_id="statsbomb_full_dynamic_ingestion",
    start_date=days_ago(1),
    schedule="@daily",
    catchup=False,
    tags=["statsbomb", "ingestion"],
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
)
def statsbomb_full_dynamic_ingestion():

    @task
    def ingest_competitions():
        """Télécharge et upload competitions.json"""
        url = f"{BASE_URL}/competitions.json"
        logging.info(f"Downloading {url}")
        r = robust_get(url)
        r.raise_for_status()
        S3Hook("minio_default").load_bytes(
            bytes_data=r.content,
            key="competitions.json",
            bucket_name=BUCKET,
            replace=True,
        )
        logging.info("Uploaded competitions.json")

    @task
    def ingest_matches():
        """
        Télécharge pour chaque competition/saison son matches/{cid}/{sid}.json et upload.
        """
        # relit competitions.json depuis GitHub
        r = robust_get(f"{BASE_URL}/competitions.json")
        r.raise_for_status()
        comps = r.json()

        hook = S3Hook("minio_default")
        for comp in comps:
            cid, sid = comp["competition_id"], comp["season_id"]
            url = f"{BASE_URL}/matches/{cid}/{sid}.json"
            key = f"matches/{cid}/{sid}.json"
            logging.info(f"Downloading {url}")
            resp = robust_get(url)
            if resp.status_code == 200:
                hook.load_bytes(
                    bytes_data=resp.content,
                    key=key,
                    bucket_name=BUCKET,
                    replace=True,
                )
                logging.info(f"Uploaded {key}")
            else:
                logging.warning(f"{url} returned {resp.status_code}, skipping.")

    @task
    def list_match_chunks() -> List[List[int]]:
        """
        Récupère tous les match_ids (en relisant les matches JSON sur GitHub),
        les découpe en paquets de CHUNK_SIZE et renvoie la liste de chunks.
        """
        match_ids: List[int] = []

        # on relit competitions pour itérer
        resp = robust_get(f"{BASE_URL}/competitions.json")
        resp.raise_for_status()
        for comp in resp.json():
            cid, sid = comp["competition_id"], comp["season_id"]
            url = f"{BASE_URL}/matches/{cid}/{sid}.json"
            r = robust_get(url)
            if r.status_code != 200:
                continue
            for m in r.json():
                match_ids.append(m["match_id"])

        # découpe
        chunks = [
            match_ids[i : i + CHUNK_SIZE]
            for i in range(0, len(match_ids), CHUNK_SIZE)
        ]
        logging.info(f"Total match_ids: {len(match_ids)}, chunks: {len(chunks)}")
        return chunks

    @task
    def fetch_and_upload_chunk(match_ids: List[int]):
        """
        Pour chaque match_id du chunk, télécharge events et lineups et upload.
        """
        hook = S3Hook("minio_default")
        for mid in match_ids:
            for sub in ("events", "lineups"):
                url = f"{BASE_URL}/{sub}/{mid}.json"
                logging.info(f"Downloading {url}")
                r = robust_get(url)
                if r.status_code == 200:
                    key = f"{sub}/{mid}.json"
                    hook.load_bytes(
                        bytes_data=r.content,
                        key=key,
                        bucket_name=BUCKET,
                        replace=True,
                    )
                    logging.info(f"Uploaded s3://{BUCKET}/{key}")
                else:
                    logging.warning(f"{url} returned {r.status_code}, skipping.")

    # Orchestration
    comp = ingest_competitions()
    mat = ingest_matches()
    chunks = list_match_chunks()
    # on attend bien que ingest_matches soit terminé avant de découper les events
    comp >> mat >> chunks
    fetch_and_upload_chunk.expand(match_ids=chunks)

dag = statsbomb_full_dynamic_ingestion()
