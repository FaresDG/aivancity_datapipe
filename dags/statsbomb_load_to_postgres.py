# statsbomb_load_to_postgres.py

import json
import logging
import time                          # <--- correction ici (au lieu de "from time")
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


def load_events():
    s3 = S3Hook("minio_default")
    pg = PostgresHook("postgres_default")

    # 1) On récupère tous les match_id valides en base
    existing_matches = pg.get_records("SELECT match_id FROM matches")
    valid_ids = {r[0] for r in existing_matches}
    logging.info("Events: %d valid match IDs", len(valid_ids))

    # 2) On liste toutes les clés S3 dans le préfixe "events/"
    keys = s3.list_keys(bucket_name=BUCKET, prefix="events/") or []
    logging.info("Found %d event files in bucket", len(keys))

    # 3) On segmente en petits lots pour ne pas échouer sur un trop gros batch
    chunk_size = 200
    chunks = [keys[i : i + chunk_size] for i in range(0, len(keys), chunk_size)]

    for chunk_index, chunk in enumerate(chunks, start=1):
        logging.info(
            "Processing chunk %d/%d (files %d)",
            chunk_index,
            len(chunks),
            len(chunk),
        )
        batch = []

        for i, key in enumerate(chunk, start=1):
            if i % 100 == 0:
                logging.info(
                    "Chunk %d/%d — processed %d/%d files…",
                    chunk_index,
                    len(chunks),
                    i,
                    len(chunk),
                )

            # 3.a) Lecture du JSON depuis MinIO
            try:
                raw = s3.read_key(key=key, bucket_name=BUCKET)
            except Exception as e:
                logging.warning(f"Impossible de lire '{key}' : {e}, on skip.")
                continue

            try:
                arr = json.loads(raw)
            except Exception as e:
                logging.warning(f"Erreur JSON pour '{key}' : {e}, on skip.")
                continue

            # 3.b) On tente d’extraire le match_id depuis le nom de fichier
            file_mid = int(key.split("/")[-1].replace(".json", ""))

            # 3.c) Pour chaque événement dans le fichier
            for ev in arr:
                # On remonte mid = ev["match_id"] si présent sinon file_mid
                mid = ev.get("match_id") or file_mid
                if mid not in valid_ids:
                    continue

                # ─────────────────────
                # 4) Extraction de TOUTES les colonnes
                # ─────────────────────

                # 4.1) Clés génériques + ref match
                event_id = ev.get("id")
                index_ = ev.get("index")                                # “index” dans le JSON
                period = ev.get("period")
                timestamp = ev.get("timestamp")
                minute = ev.get("minute")
                second = ev.get("second")

                # 4.2) Type d’événement
                type_obj = ev.get("type") or {}
                type_id = type_obj.get("id")
                type_name = type_obj.get("name")

                # 4.3) Possession
                possession = ev.get("possession")
                poss_team = ev.get("possession_team") or {}
                possession_team_id = poss_team.get("id")
                possession_team_name = poss_team.get("name")

                # 4.4) Play pattern
                pp = ev.get("play_pattern") or {}
                play_pattern_id = pp.get("id")
                play_pattern_name = pp.get("name")

                # 4.5) Équipe
                team_obj = ev.get("team") or {}
                team_id = team_obj.get("id")
                team_name = team_obj.get("name")

                # 4.6) Joueur (lorsque l’événement en a un)
                player = ev.get("player") or {}
                player_id = player.get("id")
                player_name = player.get("name")

                # 4.7) Position sur le terrain
                pos = ev.get("position") or {}
                position_id = pos.get("id")
                position_name = pos.get("name")

                # 4.8) Localisation + durée + flags
                loc = ev.get("location") if isinstance(ev.get("location"), list) else [None, None]
                location_x = loc[0]
                location_y = loc[1]
                duration = ev.get("duration")
                under_pressure = ev.get("under_pressure", False)
                off_camera = ev.get("off_camera", False)
                out_flag = ev.get("out", False)

                # 4.9) Related events + tactics + event_details
                related = ev.get("related_events") or []
                tactics = ev.get("tactics") or {}

                # On construit event_details en retirant toutes les clés qu’on a déjà mappées
                details = {
                    k: v
                    for k, v in ev.items()
                    if k
                    not in [
                        "id",
                        "match_id",
                        "index",
                        "period",
                        "timestamp",
                        "minute",
                        "second",
                        "type",
                        "possession",
                        "possession_team",
                        "play_pattern",
                        "team",
                        "player",
                        "position",
                        "location",
                        "duration",
                        "under_pressure",
                        "off_camera",
                        "out",
                        "related_events",
                        "tactics",
                        "pass",
                        "carry",
                        "dribble",
                        "ball_receipt",
                        "shot",
                        "pressure",
                        "50/50",
                        "block",
                        "clearance",
                        "dribbled_past",
                        "duel",
                        "foul_committed",
                        "foul_won",
                        "goalkeeper_position",
                        "goalkeeper_technique",
                        "goalkeeper_body_part",
                        "goalkeeper_type",
                        "goalkeeper_outcome",
                        "interception",
                        "miscontrol",
                        "ball_recovery",
                        "substitution",
                        "player_off",
                        "bad_behaviour",
                    ]
                }

                # ──────────────────────────────────────────
                # 5) Sous-objets selon type_name
                # ──────────────────────────────────────────

                # 5.1) PASS
                p = ev.get("pass") or {}
                pass_recipient = p.get("recipient") or {}
                pass_recipient_id = pass_recipient.get("id")
                pass_recipient_name = pass_recipient.get("name")
                pass_length = p.get("length")
                pass_angle = p.get("angle")
                h = p.get("height") or {}
                pass_height_id = h.get("id")
                pass_height_name = h.get("name")
                pel = p.get("end_location") or [None, None]
                pass_end_location_x = pel[0]
                pass_end_location_y = pel[1]
                bp = p.get("body_part") or {}
                pass_body_part_id = bp.get("id")
                pass_body_part_name = bp.get("name")
                pt = p.get("type") or {}
                pass_type_id = pt.get("id")
                pass_type_name = pt.get("name")
                po = p.get("outcome") or {}
                pass_outcome_id = po.get("id")
                pass_outcome_name = po.get("name")
                assisted_shot_id = p.get("assisted_shot_id")
                backheel = p.get("backheel", False)
                deflected = p.get("deflected", False)
                miscommunication = p.get("miscommunication", False)
                cross = p.get("cross", False)
                cut_back = p.get("cut_back", False)
                switch = p.get("switch", False)
                shot_assist = p.get("shot_assist", False)
                goal_assist = p.get("goal_assist", False)
                ptc = p.get("technique") or {}
                pass_technique_id = ptc.get("id")
                pass_technique_name = ptc.get("name")
                pass_is_out = (pass_outcome_name == "Out")

                # 5.2) CARRY
                c = ev.get("carry") or {}
                cel = c.get("end_location") or [None, None]
                carry_end_location_x = cel[0]
                carry_end_location_y = cel[1]
                carry_overrun = c.get("overrun", False)
                carry_nutmeg = c.get("nutmeg", False)

                # 5.3) DRIBBLE
                d = ev.get("dribble") or {}
                do = d.get("outcome") or {}
                dribble_outcome_id = do.get("id")
                dribble_outcome_name = do.get("name")
                dribble_overrun = d.get("overrun", False)
                dribble_nutmeg = d.get("nutmeg", False)
                dribble_no_touch = d.get("no_touch", False)

                # 5.4) BALL RECEIPT*
                br = ev.get("ball_receipt") or {}
                bro = br.get("outcome") or {}
                ball_receipt_outcome_id = bro.get("id")
                ball_receipt_outcome_name = bro.get("name")

                # 5.5) SHOT
                s = ev.get("shot") or {}
                sbp = s.get("body_part") or {}
                shot_body_part_id = sbp.get("id")
                shot_body_part_name = sbp.get("name")
                shot_statsbomb_xg = s.get("statsbomb_xg")
                so = s.get("outcome") or {}
                shot_outcome_id = so.get("id")
                shot_outcome_name = so.get("name")
                sel = s.get("end_location") or [None, None, None]
                shot_end_location_x = sel[0]
                shot_end_location_y = sel[1]
                shot_end_location_z = sel[2] if len(sel) > 2 else None
                shot_key_pass_id = s.get("key_pass_id")
                shot_aerial_won = s.get("aerial_won", False)
                shot_follows_dribble = s.get("follows_dribble", False)
                shot_first_time = s.get("first_time", False)
                shot_open_goal = s.get("open_goal", False)
                shot_deflected = s.get("deflected", False)
                sht_tech = s.get("technique") or {}
                shot_technique_id = sht_tech.get("id")
                shot_technique_name = sht_tech.get("name")
                shot_stats_frame = json.dumps(s.get("freeze_frame") or [])

                # 5.6) PRESSURE
                pr = ev.get("pressure") or {}
                pressure_counterpress = pr.get("counterpress", False)

                # 5.7) 50/50
                f5050 = ev.get("50/50") or {}
                duel_5050_outcome = f5050.get("outcome") or {}
                duel_5050_outcome_id = duel_5050_outcome.get("id")
                duel_5050_outcome_name = duel_5050_outcome.get("name")
                duel_5050_counterpress = f5050.get("counterpress", False)

                # 5.8) BLOCK
                bl = ev.get("block") or {}
                block_deflection = bl.get("deflection", False)
                block_offensive = bl.get("offensive", False)
                block_save_block = bl.get("save_block", False)
                block_counterpress = bl.get("counterpress", False)

                # 5.9) CLEARANCE
                cl = ev.get("clearance") or {}
                clearance_aerial_won = cl.get("aerial_won", False)
                cbp = cl.get("body_part") or {}
                clearance_body_part_id = cbp.get("id")
                clearance_body_part_name = cbp.get("name")

                # 5.10) DRIBBLED PAST
                dp = ev.get("dribbled_past") or {}
                dribbled_past_counterpress = dp.get("counterpress", False)

                # 5.11) DUEL
                du = ev.get("duel") or {}
                duel_counterpress = du.get("counterpress", False)
                dt = du.get("type") or {}
                duel_type_id = dt.get("id")
                duel_type_name = dt.get("name")
                do2 = du.get("outcome") or {}
                duel_outcome_id = do2.get("id")
                duel_outcome_name = do2.get("name")

                # 5.12) FOUL COMMITTED
                fc = ev.get("foul_committed") or {}
                foul_committed_counterpress = fc.get("counterpress", False)
                foul_committed_offensive = fc.get("offensive", False)
                fct = fc.get("type") or {}
                foul_committed_type_id = fct.get("id")
                foul_committed_type_name = fct.get("name")
                foul_committed_advantage = fc.get("advantage", False)
                foul_committed_penalty = fc.get("penalty", False)
                fcc = fc.get("card") or {}
                foul_committed_card_id = fcc.get("id")
                foul_committed_card_name = fcc.get("name")

                # 5.13) FOUL WON
                fw = ev.get("foul_won") or {}
                foul_won_defensive = fw.get("defensive", False)
                foul_won_advantage = fw.get("advantage", False)
                foul_won_penalty = fw.get("penalty", False)

                # 5.14) GOALKEEPER
                gkpos = ev.get("goalkeeper_position") or {}
                goalkeeper_position_id = gkpos.get("id")
                goalkeeper_position_name = gkpos.get("name")
                gktech = ev.get("goalkeeper_technique") or {}
                goalkeeper_technique_id = gktech.get("id")
                goalkeeper_technique_name = gktech.get("name")
                gkbp = ev.get("goalkeeper_body_part") or {}
                goalkeeper_body_part_id = gkbp.get("id")
                goalkeeper_body_part_name = gkbp.get("name")
                gkt = ev.get("goalkeeper_type") or {}
                goalkeeper_type_id = gkt.get("id")
                goalkeeper_type_name = gkt.get("name")
                gko = ev.get("goalkeeper_outcome") or {}
                goalkeeper_outcome_id = gko.get("id")
                goalkeeper_outcome_name = gko.get("name")

                # 5.15) INTERCEPTION
                inter = ev.get("interception") or {}
                interception_outcome = inter.get("outcome") or {}
                interception_outcome_id = interception_outcome.get("id")
                interception_outcome_name = interception_outcome.get("name")
                interception_counterpress = inter.get("counterpress", False)

                # 5.16) MISCONTROL
                mc = ev.get("miscontrol") or {}
                miscontrol_aerial_won = mc.get("aerial_won", False)

                # 5.17) BALL RECOVERY
                br2 = ev.get("ball_recovery") or {}
                ball_recovery_offensive = br2.get("offensive", False)
                ball_recovery_failure = br2.get("recovery_failure", False)

                # 5.18) SUBSTITUTION
                sub = ev.get("substitution") or {}
                sr = sub.get("replacement") or {}
                substitution_replacement_id = sr.get("id")
                substitution_replacement_name = sr.get("name")
                so2 = sub.get("outcome") or {}
                substitution_outcome_id = so2.get("id")
                substitution_outcome_name = so2.get("name")

                # 5.19) PLAYER OFF
                poff = ev.get("player_off") or {}
                player_off_permanent = poff.get("permanent", False)

                # 5.20) BAD BEHAVIOUR
                bb = ev.get("bad_behaviour") or {}
                bc = bb.get("card") or {}
                bad_behaviour_card_id = bc.get("id")
                bad_behaviour_card_name = bc.get("name")

                # ────────────────────────────────────────────────────
                # 6) On crée le tuple de toutes les colonnes, dans l’ordre EXACT du schéma SQL
                # ────────────────────────────────────────────────────
                batch.append(
                    (
                        # 1) event_id, match_id
                        event_id,
                        mid,
                        # 2) index, period, timestamp, minute, second
                        index_,
                        period,
                        timestamp,
                        minute,
                        second,
                        # 3) type_id, type_name
                        type_id,
                        type_name,
                        # 4) possession, possession_team_id, possession_team_name
                        possession,
                        possession_team_id,
                        possession_team_name,
                        # 5) play_pattern_id, play_pattern_name
                        play_pattern_id,
                        play_pattern_name,
                        # 6) team_id, team_name
                        team_id,
                        team_name,
                        # 7) player_id, player_name
                        player_id,
                        player_name,
                        # 8) position_id, position_name
                        position_id,
                        position_name,
                        # 9) location_x, location_y, duration, under_pressure, off_camera, out
                        location_x,
                        location_y,
                        duration,
                        under_pressure,
                        off_camera,
                        out_flag,
                        # 10) related_events, tactics
                        json.dumps(related),
                        json.dumps(tactics),
                        # 11) PASS
                        pass_recipient_id,
                        pass_recipient_name,
                        pass_length,
                        pass_angle,
                        pass_height_id,
                        pass_height_name,
                        pass_end_location_x,
                        pass_end_location_y,
                        pass_body_part_id,
                        pass_body_part_name,
                        pass_type_id,
                        pass_type_name,
                        pass_outcome_id,
                        pass_outcome_name,
                        assisted_shot_id,
                        backheel,
                        deflected,
                        miscommunication,
                        cross,
                        cut_back,
                        switch,
                        shot_assist,
                        goal_assist,
                        pass_technique_id,
                        pass_technique_name,
                        pass_is_out,
                        # 12) CARRY
                        carry_end_location_x,
                        carry_end_location_y,
                        carry_overrun,
                        carry_nutmeg,
                        # 13) DRIBBLE
                        dribble_outcome_id,
                        dribble_outcome_name,
                        dribble_overrun,
                        dribble_nutmeg,
                        dribble_no_touch,
                        # 14) BALL RECEIPT*
                        ball_receipt_outcome_id,
                        ball_receipt_outcome_name,
                        # 15) SHOT
                        shot_body_part_id,
                        shot_body_part_name,
                        shot_statsbomb_xg,
                        shot_outcome_id,
                        shot_outcome_name,
                        shot_end_location_x,
                        shot_end_location_y,
                        shot_end_location_z,
                        shot_key_pass_id,
                        shot_aerial_won,
                        shot_follows_dribble,
                        shot_first_time,
                        shot_open_goal,
                        shot_deflected,
                        shot_technique_id,
                        shot_technique_name,
                        shot_stats_frame,
                        # 16) PRESSURE
                        pressure_counterpress,
                        # 17) 50/50
                        duel_5050_outcome_id,
                        duel_5050_outcome_name,
                        duel_5050_counterpress,
                        # 18) BLOCK
                        block_deflection,
                        block_offensive,
                        block_save_block,
                        block_counterpress,
                        # 19) CLEARANCE
                        clearance_aerial_won,
                        clearance_body_part_id,
                        clearance_body_part_name,
                        # 20) DRIBBLED PAST
                        dribbled_past_counterpress,
                        # 21) DUEL
                        duel_counterpress,
                        duel_type_id,
                        duel_type_name,
                        duel_outcome_id,
                        duel_outcome_name,
                        # 22) FOUL COMMITTED
                        foul_committed_counterpress,
                        foul_committed_offensive,
                        foul_committed_type_id,
                        foul_committed_type_name,
                        foul_committed_advantage,
                        foul_committed_penalty,
                        foul_committed_card_id,
                        foul_committed_card_name,
                        # 23) FOUL WON
                        foul_won_defensive,
                        foul_won_advantage,
                        foul_won_penalty,
                        # 24) GOALKEEPER
                        goalkeeper_position_id,
                        goalkeeper_position_name,
                        goalkeeper_technique_id,
                        goalkeeper_technique_name,
                        goalkeeper_body_part_id,
                        goalkeeper_body_part_name,
                        goalkeeper_type_id,
                        goalkeeper_type_name,
                        goalkeeper_outcome_id,
                        goalkeeper_outcome_name,
                        # 25) INTERCEPTION
                        interception_outcome_id,
                        interception_outcome_name,
                        interception_counterpress,
                        # 26) MISCONTROL
                        miscontrol_aerial_won,
                        # 27) BALL RECOVERY
                        ball_recovery_offensive,
                        ball_recovery_failure,
                        # 28) SUBSTITUTION
                        substitution_replacement_id,
                        substitution_replacement_name,
                        substitution_outcome_id,
                        substitution_outcome_name,
                        # 29) PLAYER OFF
                        player_off_permanent,
                        # 30) BAD BEHAVIOUR
                        bad_behaviour_card_id,
                        bad_behaviour_card_name,
                        # 31) CHAMPS JSON additionnels
                        json.dumps(details),
                    )
                )

        # 6) On insère le batch une fois terminé
        if batch:
            pg.insert_rows(
                table="events",
                rows=batch,
                target_fields=[
                    # 1) Clé primaire + ref match
                    "event_id",
                    "match_id",
                    # 2) index, period, timestamp, minute, second
                    '"index"',
                    "period",
                    "timestamp",
                    "minute",
                    "second",
                    # 3) type_id, type_name
                    "type_id",
                    "type_name",
                    # 4) possession + team
                    "possession",
                    "possession_team_id",
                    "possession_team_name",
                    # 5) play_pattern
                    "play_pattern_id",
                    "play_pattern_name",
                    # 6) team
                    "team_id",
                    "team_name",
                    # 7) player
                    "player_id",
                    "player_name",
                    # 8) position
                    "position_id",
                    "position_name",
                    # 9) location + durée + flags
                    "location_x",
                    "location_y",
                    "duration",
                    "under_pressure",
                    "off_camera",
                    "out",
                    # 10) related_events + tactics
                    "related_events",
                    "tactics",
                    # 11) PASS
                    "pass_recipient_id",
                    "pass_recipient_name",
                    "pass_length",
                    "pass_angle",
                    "pass_height_id",
                    "pass_height_name",
                    "pass_end_location_x",
                    "pass_end_location_y",
                    "pass_body_part_id",
                    "pass_body_part_name",
                    "pass_type_id",
                    "pass_type_name",
                    "pass_outcome_id",
                    "pass_outcome_name",
                    "assisted_shot_id",
                    "backheel",
                    "deflected",
                    "miscommunication",
                    '"cross"',
                    "cut_back",
                    '"switch"',
                    "shot_assist",
                    "goal_assist",
                    "pass_technique_id",
                    "pass_technique_name",
                    '"is_out"',
                    # 12) CARRY
                    "carry_end_location_x",
                    "carry_end_location_y",
                    "carry_overrun",
                    "carry_nutmeg",
                    # 13) DRIBBLE
                    "dribble_outcome_id",
                    "dribble_outcome_name",
                    "dribble_overrun",
                    "dribble_nutmeg",
                    "dribble_no_touch",
                    # 14) BALL RECEIPT*
                    "ball_receipt_outcome_id",
                    "ball_receipt_outcome_name",
                    # 15) SHOT
                    "shot_body_part_id",
                    "shot_body_part_name",
                    "shot_statsbomb_xg",
                    "shot_outcome_id",
                    "shot_outcome_name",
                    "shot_end_location_x",
                    "shot_end_location_y",
                    "shot_end_location_z",
                    "shot_key_pass_id",
                    "shot_aerial_won",
                    "shot_follows_dribble",
                    "shot_first_time",
                    "shot_open_goal",
                    "shot_deflected",
                    "shot_technique_id",
                    "shot_technique_name",
                    "shot_stats_frame",
                    # 16) PRESSURE
                    "pressure_counterpress",
                    # 17) 50/50
                    "duel_5050_outcome_id",
                    "duel_5050_outcome_name",
                    "duel_5050_counterpress",
                    # 18) BLOCK
                    "block_deflection",
                    "block_offensive",
                    "block_save_block",
                    "block_counterpress",
                    # 19) CLEARANCE
                    "clearance_aerial_won",
                    "clearance_body_part_id",
                    "clearance_body_part_name",
                    # 20) DRIBBLED PAST
                    "dribbled_past_counterpress",
                    # 21) DUEL
                    "duel_counterpress",
                    "duel_type_id",
                    "duel_type_name",
                    "duel_outcome_id",
                    "duel_outcome_name",
                    # 22) FOUL COMMITTED
                    "foul_committed_counterpress",
                    "foul_committed_offensive",
                    "foul_committed_type_id",
                    "foul_committed_type_name",
                    "foul_committed_advantage",
                    "foul_committed_penalty",
                    "foul_committed_card_id",
                    "foul_committed_card_name",
                    # 23) FOUL WON
                    "foul_won_defensive",
                    "foul_won_advantage",
                    "foul_won_penalty",
                    # 24) GOALKEEPER
                    "goalkeeper_position_id",
                    "goalkeeper_position_name",
                    "goalkeeper_technique_id",
                    "goalkeeper_technique_name",
                    "goalkeeper_body_part_id",
                    "goalkeeper_body_part_name",
                    "goalkeeper_type_id",
                    "goalkeeper_type_name",
                    "goalkeeper_outcome_id",
                    "goalkeeper_outcome_name",
                    # 25) INTERCEPTION
                    "interception_outcome_id",
                    "interception_outcome_name",
                    "interception_counterpress",
                    # 26) MISCONTROL
                    "miscontrol_aerial_won",
                    # 27) BALL RECOVERY
                    "ball_recovery_offensive",
                    "ball_recovery_failure",
                    # 28) SUBSTITUTION
                    "substitution_replacement_id",
                    "substitution_replacement_name",
                    "substitution_outcome_id",
                    "substitution_outcome_name",
                    # 29) PLAYER OFF
                    "player_off_permanent",
                    # 30) BAD BEHAVIOUR
                    "bad_behaviour_card_id",
                    "bad_behaviour_card_name",
                    # 31) Champs JSON additionnels
                    "event_details",
                ],
                commit_every=20,
            )
            logging.info(
                "Chunk %d/%d : inséré %d lignes dans events.",
                chunk_index,
                len(chunks),
                len(batch),
            )
        else:
            logging.info("Chunk %d/%d : aucun événement à insérer.", chunk_index, len(chunk))

        # 7) On fait une pause rapide pour libérer le scheduler
        time.sleep(1)

    logging.info("load_events: traitement complet des fichiers terminé.")


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
        execution_timeout=timedelta(hours=8),
        retries=2,
        retry_delay=timedelta(minutes=10),
    )

    t1 >> t2 >> [t3, t4]
