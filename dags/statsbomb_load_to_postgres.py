import json
from datetime import timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# IDs des compétitions à charger : Champions League (16) + La Liga (11)
COMP_IDS = [16, 11]

# Bucket S3/MinIO où sont stockés les JSON
BUCKET = Variable.get("STATSBOMB_BUCKET", default_var="statsbomb")

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def upsert_competitions():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    comps = json.loads(s3.read_key("competitions.json", BUCKET))
    rows = [c for c in comps if c["competition_id"] in COMP_IDS]

    # Clés existantes pour nos compétitions
    existing = pg.get_records(
        "SELECT competition_id, season_id FROM competitions WHERE competition_id = ANY(%s)",
        parameters=(COMP_IDS,)
    )
    exist_set = {(c, s) for c, s in existing}

    to_insert, to_update = [], []
    for c in rows:
        key = (c["competition_id"], c["season_id"])
        if key in exist_set:
            to_update.append(c)
        else:
            to_insert.append(c)

    # Batch insert des nouveaux
    if to_insert:
        pg.insert_rows(
            table="competitions",
            rows=[
                (
                    c["competition_id"], c["season_id"], c["competition_name"],
                    c["competition_gender"], c["country_name"], c["season_name"],
                    c["match_updated"], c["match_available"],
                )
                for c in to_insert
            ],
            target_fields=[
                "competition_id", "season_id", "competition_name", "competition_gender",
                "country_name", "season_name", "match_updated", "match_available",
            ],
            commit_every=100,
        )

    # Update des existants
    for c in to_update:
        pg.run(
            """
            UPDATE competitions SET
                competition_name   = %(competition_name)s,
                competition_gender = %(competition_gender)s,
                country_name       = %(country_name)s,
                season_name        = %(season_name)s,
                match_updated      = %(match_updated)s,
                match_available    = %(match_available)s
            WHERE competition_id = %(competition_id)s
              AND season_id      = %(season_id)s
            """,
            parameters=c,
        )


def load_matches():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    # Récupère les match_id existants
    existing = pg.get_records("SELECT match_id FROM matches")
    exist_ids = {row[0] for row in existing}

    to_insert, to_update = [], []

    # Pour chaque compétition de COMP_IDS, on pioche ses fichiers
    for cid in COMP_IDS:
        keys = s3.list_keys(bucket_name=BUCKET, prefix=f"matches/{cid}/") or []
        for key in keys:
            raw = s3.read_key(key=key, bucket_name=BUCKET)
            arr = json.loads(raw)
            _, _, sid_file = key.split("/")
            season_id = int(sid_file.replace(".json", ""))

            for m in arr:
                params = {
                    "match_id":               m.get("match_id"),
                    "competition_id":         cid,
                    "season_id":              season_id,
                    "match_date":             m.get("match_date"),
                    "kick_off":               m.get("kick_off"),
                    "stadium_id":             m.get("stadium", {}).get("id"),
                    "stadium_name":           m.get("stadium", {}).get("name"),
                    "stadium_country":        m.get("stadium_country"),
                    "referee_id":             m.get("referee", {}).get("id"),
                    "referee_name":           m.get("referee", {}).get("name"),
                    "referee_country":        (m.get("referee_country") or {}).get("name"),
                    "home_team_id":           m.get("home_team", {}).get("id"),
                    "home_team_name":         m.get("home_team", {}).get("name"),
                    "home_team_gender":       m.get("home_team_gender"),
                    "away_team_id":           m.get("away_team", {}).get("id"),
                    "away_team_name":         m.get("away_team", {}).get("name"),
                    "away_team_gender":       m.get("away_team_gender"),
                    "home_score":             m.get("home_score"),
                    "away_score":             m.get("away_score"),
                    "match_status":           m.get("match_status"),
                    "match_week":             m.get("match_week"),
                    "competition_stage_id":   m.get("competition_stage", {}).get("id"),
                    "competition_stage_name": m.get("competition_stage", {}).get("name"),
                    "last_updated":           m.get("last_updated"),
                    "metadata":               json.dumps(m.get("metadata", {})),
                }
                tpl = tuple(params[f] for f in [
                    "match_id","competition_id","season_id","match_date","kick_off",
                    "stadium_id","stadium_name","stadium_country",
                    "referee_id","referee_name","referee_country",
                    "home_team_id","home_team_name","home_team_gender",
                    "away_team_id","away_team_name","away_team_gender",
                    "home_score","away_score","match_status","match_week",
                    "competition_stage_id","competition_stage_name","last_updated","metadata"
                ])
                if params["match_id"] in exist_ids:
                    to_update.append(params)
                else:
                    to_insert.append(tpl)

    # Insert des nouveaux
    if to_insert:
        pg.insert_rows(
            table="matches",
            rows=to_insert,
            target_fields=[
                "match_id","competition_id","season_id","match_date","kick_off",
                "stadium_id","stadium_name","stadium_country",
                "referee_id","referee_name","referee_country",
                "home_team_id","home_team_name","home_team_gender",
                "away_team_id","away_team_name","away_team_gender",
                "home_score","away_score","match_status","match_week",
                "competition_stage_id","competition_stage_name","last_updated","metadata"
            ],
            commit_every=200,
        )

    # Update des existants (scores et last_updated)
    for u in to_update:
        pg.run(
            """
            UPDATE matches SET
                home_score   = %(home_score)s,
                away_score   = %(away_score)s,
                last_updated = %(last_updated)s
            WHERE match_id = %(match_id)s
            """,
            parameters=u,
        )


def load_lineups():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    # match_id valides pour nos compétitions
    existing = pg.get_records(
        "SELECT match_id FROM matches WHERE competition_id = ANY(%s)",
        parameters=(COMP_IDS,)
    )
    valid_ids = {r[0] for r in existing}

    keys = s3.list_keys(bucket_name=BUCKET, prefix="lineups/") or []
    batch = []

    for key in keys:
        mid = int(key.split("/")[-1].replace(".json", ""))
        if mid not in valid_ids:
            continue
        arr = json.loads(s3.read_key(key=key, bucket_name=BUCKET))
        for team in arr:
            for p in team.get("lineup", []):
                batch.append((
                    mid,
                    team.get("team_id"),
                    p.get("player_id"),
                    p.get("player_name"),
                    p.get("player_nickname"),
                    p.get("jersey_number"),
                    p.get("country", {}).get("id"),
                    p.get("country", {}).get("name"),
                ))

    if batch:
        pg.insert_rows(
            table="lineups",
            rows=batch,
            target_fields=[
                "match_id","team_id","player_id","player_name","player_nickname",
                "jersey_number","country_id","country_name"
            ],
            commit_every=200,
        )


def load_events():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    # match_id valides pour nos compétitions
    existing = pg.get_records(
        "SELECT match_id FROM matches WHERE competition_id = ANY(%s)",
        parameters=(COMP_IDS,)
    )
    valid_ids = {r[0] for r in existing}

    keys = s3.list_keys(bucket_name=BUCKET, prefix="events/") or []
    batch = []

    for key in keys:
        file_mid = int(key.split("/")[-1].replace(".json", ""))
        arr = json.loads(s3.read_key(key=key, bucket_name=BUCKET))
        for ev in arr:
            mid = ev.get("match_id") or file_mid
            if mid not in valid_ids:
                continue
            details = {
                k: v for k, v in ev.items() if k not in [
                    "id","match_id","period","timestamp","team","player",
                    "position","location","duration","under_pressure",
                    "off_camera","play_pattern","related_events","type"
                ]
            }
            batch.append((
                ev.get("id"), mid, ev.get("period"), ev.get("timestamp"),
                ev.get("team", {}).get("id"), ev.get("team", {}).get("name"),
                ev.get("player", {}).get("id"), ev.get("player", {}).get("name"),
                ev.get("position", {}).get("id"), ev.get("position", {}).get("name"),
                ev.get("location", [None, None])[0], ev.get("location", [None, None])[1],
                ev.get("duration"), ev.get("under_pressure", False), ev.get("off_camera", False),
                ev.get("play_pattern", {}).get("id"), ev.get("play_pattern", {}).get("name"),
                json.dumps(ev.get("related_events", [])), ev.get("type", {}).get("name"),
                json.dumps(details),
            ))

    if batch:
        pg.insert_rows(
            table="events",
            rows=batch,
            target_fields=[
                "event_id","match_id","period","timestamp","team_id","team_name",
                "player_id","player_name","position_id","position_name",
                "location_x","location_y","duration","under_pressure",
                "off_camera","play_pattern_id","play_pattern_name",
                "related_events","event_type","event_details"
            ],
            commit_every=500,
        )


with DAG(
    dag_id="statsbomb_load_postgres_champions",
    default_args=default_args,
    description="Charge la Champions League (16) et la Liga (11) de MinIO vers PostgreSQL",
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["statsbomb", "champions", "laliga", "load"],
) as dag:

    t1 = PythonOperator(
        task_id="upsert_competitions",
        python_callable=upsert_competitions
    )
    t2 = PythonOperator(
        task_id="load_matches",
        python_callable=load_matches
    )
    t3 = PythonOperator(
        task_id="load_lineups",
        python_callable=load_lineups
    )
    t4 = PythonOperator(
        task_id="load_events",
        python_callable=load_events
    )

    t1 >> t2 >> [t3, t4]
