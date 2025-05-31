# statsbomb_load_to_postgres.py

import json
import logging
from datetime import timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# bucket MinIO/S3
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

    logging.info("Reading competitions.json from bucket %s", BUCKET)
    comps = json.loads(s3.read_key("competitions.json", BUCKET))

    # Clés existantes
    existing = pg.get_records("SELECT competition_id, season_id FROM competitions")
    exist_set = {(c, s) for c, s in existing}

    to_insert, to_update = [], []
    for c in comps:
        key = (c["competition_id"], c["season_id"])
        if key in exist_set:
            to_update.append(c)
        else:
            to_insert.append(c)

    logging.info("Will insert %d new competitions, update %d existing", len(to_insert), len(to_update))

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

    # On récupère tous les competition_id
    comps = pg.get_records("SELECT DISTINCT competition_id FROM competitions")
    comp_ids = [c[0] for c in comps]

    # IDs déjà en base
    existing = pg.get_records("SELECT match_id FROM matches")
    exist_ids = {r[0] for r in existing}

    to_insert, to_update = [], []

    for cid in comp_ids:
        keys = s3.list_keys(bucket_name=BUCKET, prefix=f"matches/{cid}/") or []
        for key in keys:
            arr = json.loads(s3.read_key(key=key, bucket_name=BUCKET))
            _, _, sid_file = key.split("/")
            season_id = int(sid_file.replace(".json", ""))

            for m in arr:
                params = {
                    "match_id":               m["match_id"],
                    "competition_id":         cid,
                    "season_id":              season_id,
                    "match_date":             m.get("match_date"),
                    "kick_off":               m.get("kick_off"),
                    "stadium_id":             m.get("stadium", {}).get("id"),
                    "stadium_name":           m.get("stadium", {}).get("name"),
                    "stadium_country":        m.get("stadium", {}).get("country", {}).get("name"),
                    "referee_id":             m.get("referee", {}).get("id"),
                    "referee_name":           m.get("referee", {}).get("name"),
                    "referee_country":        m.get("referee", {}).get("country", {}).get("name"),
                    "home_team_id":           m.get("home_team", {}).get("home_team_id"),
                    "home_team_name":         m.get("home_team", {}).get("home_team_name"),
                    "home_team_gender":       m.get("home_team", {}).get("home_team_gender"),

                    "away_team_id":           m.get("away_team", {}).get("away_team_id"),
                    "away_team_name":         m.get("away_team", {}).get("away_team_name"),
                    "away_team_gender":       m.get("away_team", {}).get("away_team_gender"),

                    "home_score":             m.get("home_score"),
                    "away_score":             m.get("away_score"),
                    "match_status":           m.get("match_status"),
                    "match_week":             m.get("match_week"),
                    "competition_stage_id":   m.get("competition_stage", {}).get("id"),
                    "competition_stage_name": m.get("competition_stage", {}).get("name"),
                    "last_updated":           m.get("last_updated"),
                    "metadata":               json.dumps(m.get("metadata", {})),
                }
                tpl = tuple(params[col] for col in [
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

    # INSERT complet
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

    # UPDATE complet (au moins pour les scores + last_updated)
    for u in to_update:
        pg.run(
            """
            UPDATE matches SET
                competition_id         = %(competition_id)s,
                season_id              = %(season_id)s,
                match_date             = %(match_date)s,
                kick_off               = %(kick_off)s,
                stadium_id             = %(stadium_id)s,
                stadium_name           = %(stadium_name)s,
                stadium_country        = %(stadium_country)s,
                referee_id             = %(referee_id)s,
                referee_name           = %(referee_name)s,
                referee_country        = %(referee_country)s,
                home_team_id           = %(home_team_id)s,
                home_team_name         = %(home_team_name)s,
                home_team_gender       = %(home_team_gender)s,
                away_team_id           = %(away_team_id)s,
                away_team_name         = %(away_team_name)s,
                away_team_gender       = %(away_team_gender)s,
                home_score             = %(home_score)s,
                away_score             = %(away_score)s,
                match_status           = %(match_status)s,
                match_week             = %(match_week)s,
                competition_stage_id   = %(competition_stage_id)s,
                competition_stage_name = %(competition_stage_name)s,
                last_updated           = %(last_updated)s,
                metadata               = %(metadata)s
            WHERE match_id = %(match_id)s
            """,
            parameters=u,
        )





def load_lineups():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    # 1) IDs de matchs valides
    existing_matches = pg.get_records("SELECT match_id FROM matches")
    valid_match_ids = {r[0] for r in existing_matches}
    logging.info("Lineups: %d valid match IDs", len(valid_match_ids))

    # 2) Clés existantes dans lineups pour éviter les duplicates
    existing_lineups = pg.get_records(
        "SELECT match_id, team_id, player_id FROM lineups"
    )
    exist_set = {tuple(r) for r in existing_lineups}
    logging.info("Lineups: %d existing rows in DB", len(exist_set))

    # 3) On liste les fichiers
    keys = s3.list_keys(bucket_name=BUCKET, prefix="lineups/") or []
    logging.info("Found %d lineup files in bucket", len(keys))

    batch = []
    for i, key in enumerate(keys, 1):
        # log intermédiaire
        if i % 500 == 0:
            logging.info("Processed %d/%d lineup files", i, len(keys))

        mid = int(key.split("/")[-1].replace(".json", ""))
        if mid not in valid_match_ids:
            continue

        arr = json.loads(s3.read_key(key=key, bucket_name=BUCKET))
        for team in arr:
            tid = team.get("team_id")
            for p in team.get("lineup", []):
                pk = (mid, tid, p.get("player_id"))
                if pk in exist_set:
                    continue
                exist_set.add(pk)  # pour dédupliquer si présent plusieurs fois dans ce run
                batch.append((
                    mid,
                    tid,
                    p.get("player_id"),
                    p.get("player_name"),
                    p.get("player_nickname"),
                    p.get("jersey_number"),
                    p.get("country", {}).get("id"),
                    p.get("country", {}).get("name"),
                ))

    logging.info("Inserting %d new lineup rows", len(batch))
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
        logging.info("Lineups insert done.")
    else:
        logging.info("No new lineups to insert.")




from time import sleep
from botocore.exceptions import EndpointConnectionError

def load_events():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    # 1) IDs de matchs valides
    existing = pg.get_records("SELECT match_id FROM matches")
    valid_ids = {r[0] for r in existing}
    logging.info("Events: %d valid match IDs", len(valid_ids))

    # 2) Lister les fichiers S3
    keys = s3.list_keys(bucket_name=BUCKET, prefix="events/") or []
    logging.info("Found %d event files in bucket", len(keys))

    batch = []
    for i, key in enumerate(keys, 1):
        if i % 500 == 0:
            logging.info("Processed %d/%d event files…", i, len(keys))

        # --- Retry de lecture S3 ---
        raw = None
        for attempt in range(1, 4):
            try:
                raw = s3.read_key(key=key, bucket_name=BUCKET)
                break
            except EndpointConnectionError as e:
                logging.warning(f"[{key}] Attempt {attempt}/3 failed: {e}")
                sleep(5)
        if raw is None:
            logging.error(f"[{key}] Skipping after 3 failed attempts")
            continue
        # --------------------------------

        arr = json.loads(raw)
        file_mid = int(key.split("/")[-1].replace(".json", ""))

        for ev in arr:
            mid = ev.get("match_id") or file_mid
            if mid not in valid_ids:
                continue

            # flags et champs de base
            is_out      = ev.get("pass", {}).get("outcome", {}).get("name") == "Out"
            minute      = ev.get("minute")
            second      = ev.get("second")
            possession  = ev.get("possession")
            poss_team   = ev.get("possession_team", {}) 
            play_pattern= ev.get("play_pattern", {})

            # localisation
            loc = ev.get("location") or [None, None]

            # détails de la passe (si présent)
            pst            = ev.get("pass", {})
            pass_recipient = pst.get("recipient", {})
            pass_end_loc   = pst.get("end_location") or [None, None]

            # détails du tir (si présent)
            sht          = ev.get("shot", {})
            shot_end_loc = sht.get("end_location") or [None, None]

            # métadonnées additionnelles
            related = ev.get("related_events", [])
            details = {
                k: v for k, v in ev.items()
                if k not in [
                    "id","match_id","period","timestamp","minute","second",
                    "team","possession_team","play_pattern","player","position",
                    "location","duration","under_pressure","off_camera",
                    "pass","shot","related_events","type"
                ]
            }

            batch.append((
                # clés
                ev.get("id"), mid, ev.get("period"), ev.get("timestamp"),
                minute, second,

                # équipe & possession
                ev.get("team", {}).get("id"), ev.get("team", {}).get("name"),
                possession,
                poss_team.get("id"), poss_team.get("name"),

                # position & localisation
                ev.get("position", {}).get("id"), ev.get("position", {}).get("name"),
                loc[0], loc[1],

                # durée & contexte
                ev.get("duration"),
                ev.get("under_pressure", False), ev.get("off_camera", False),
                is_out,

                # play pattern
                play_pattern.get("id"), play_pattern.get("name"),

                # passe
                pass_recipient.get("id"), pass_recipient.get("name"),
                pst.get("length"), pst.get("angle"),
                pst.get("height", {}).get("id"), pst.get("height", {}).get("name"),
                pass_end_loc[0], pass_end_loc[1],
                pst.get("body_part", {}).get("id"), pst.get("body_part", {}).get("name"),
                pst.get("outcome", {}).get("id"), pst.get("outcome", {}).get("name"),
                pst.get("type", {}).get("id"), pst.get("type", {}).get("name"),

                # tir
                sht.get("outcome", {}).get("id"), sht.get("outcome", {}).get("name"),
                sht.get("body_part", {}).get("id"), sht.get("body_part", {}).get("name"),
                sht.get("statsbomb_xg"),
                shot_end_loc[0], shot_end_loc[1],

                # liés & type & détails
                json.dumps(related),
                ev.get("type", {}).get("name"),
                json.dumps(details),
            ))

    logging.info("Prepared %d event rows for insert", len(batch))
    if batch:
        pg.insert_rows(
            table="events",
            rows=batch,
            target_fields=[
                "event_id","match_id","period","timestamp",
                "minute","second",
                "team_id","team_name","possession",
                "possession_team_id","possession_team_name",
                "position_id","position_name",
                "location_x","location_y",
                "duration","under_pressure","off_camera","is_out",
                "play_pattern_id","play_pattern_name",
                "pass_recipient_id","pass_recipient_name","pass_length","pass_angle",
                "pass_height_id","pass_height_name",
                "pass_end_location_x","pass_end_location_y",
                "pass_body_part_id","pass_body_part_name",
                "pass_outcome_id","pass_outcome_name",
                "pass_type_id","pass_type_name",
                "shot_outcome_id","shot_outcome_name",
                "shot_body_part_id","shot_body_part_name",
                "shot_statsbomb_xg","shot_end_location_x","shot_end_location_y",
                "related_events","event_type","event_details"
            ],
            commit_every=100,
        )
        logging.info("Events insert done.")
    else:
        logging.info("No new events to insert.")


with DAG(
    dag_id="statsbomb_load_postgres_all_competitions",
    default_args=default_args,
    description="Charge toutes les compétitions de MinIO vers PostgreSQL",
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["statsbomb", "load", "all"],
) as dag:

    t1 = PythonOperator(
        task_id="upsert_competitions",
        python_callable=upsert_competitions,
    )
    t2 = PythonOperator(
        task_id="load_matches",
        python_callable=load_matches,
    )
    t3 = PythonOperator(
        task_id="load_lineups",
        python_callable=load_lineups,
    )
    t4 = PythonOperator(
        task_id="load_events",
        python_callable=load_events,
        execution_timeout=timedelta(hours=1),
        retries=2,
        retry_delay=timedelta(minutes=10),
    )

    t1 >> t2 >> [t3, t4]