-- models/staging/stg_events.sql

{{
  config(
    materialized = 'table',
    schema       = 'staging'
  )
}}

select
  -- 1. Identifiants et contexte général
  ev.event_id                as event_id,
  ev.match_id                as match_id,
  ev.period                  as period,
  ev.timestamp::time         as event_time,

  -- 2. Équipe et possession
  ev.team_id                 as team_id,
  ev.team_name               as team_name,
  ev.possession              as possession,
  ev.possession_team_id      as possession_team_id,
  ev.possession_team_name    as possession_team_name,

  -- 3. Joueur et position
  ev.player_id               as player_id,
  ev.player_name             as player_name,
  ev.position_id             as position_id,
  ev.position_name           as position_name,

  -- 4. Localisation et contexte
  ev.location_x              as location_x,
  ev.location_y              as location_y,
  ev.duration                as duration,
  ev.under_pressure          as under_pressure,
  ev.off_camera              as off_camera,
  ev."out"                   as out_flag,          -- « balle hors-jeu »

  -- 5. Play pattern et métadonnées brutes
  ev.play_pattern_id         as play_pattern_id,
  ev.play_pattern_name       as play_pattern_name,
  ev.related_events          as related_events,
  ev.type_name              as event_type,
  ev.event_details           as event_details,

  ------------------------------------------------------------------
  -- 6. PASS (detail complet)
  ------------------------------------------------------------------
  ev.pass_recipient_id       as pass_recipient_id,
  ev.pass_recipient_name     as pass_recipient_name,
  ev.pass_length             as pass_length,
  ev.pass_angle              as pass_angle,
  ev.pass_height_id          as pass_height_id,
  ev.pass_height_name        as pass_height_name,
  ev.pass_body_part_id       as pass_body_part_id,
  ev.pass_body_part_name     as pass_body_part_name,
  ev.pass_type_id            as pass_type_id,
  ev.pass_type_name          as pass_type_name,
  ev.pass_outcome_id         as pass_outcome_id,
  ev.pass_outcome_name       as pass_outcome_name,
  -- flag calculé : TRUE si pass_outcome_name = 'Complete'
  (ev.pass_outcome_name = 'Complete') as pass_completed,
  ev.assisted_shot_id        as assisted_shot_id,
  ev.backheel                as backheel,
  ev.deflected               as deflected,
  ev.miscommunication        as miscommunication,
  ev.cross                   as pass_cross,
  ev.cut_back                as pass_cut_back,
  ev.switch                  as pass_switch,
  ev.shot_assist             as pass_shot_assist,
  ev.goal_assist             as pass_goal_assist,
  ev.pass_technique_id       as pass_technique_id,
  ev.pass_technique_name     as pass_technique_name,

  ------------------------------------------------------------------
  -- 7. CARRY (optionnel pour « Player Involvement »)
  ------------------------------------------------------------------
  ev.carry_end_location_x    as carry_end_location_x,
  ev.carry_end_location_y    as carry_end_location_y,
  ev.carry_overrun           as carry_overrun,
  ev.carry_nutmeg            as carry_nutmeg,

  ------------------------------------------------------------------
  -- 8. DRIBBLE (optionnel)
  ------------------------------------------------------------------
  ev.dribble_outcome_id      as dribble_outcome_id,
  ev.dribble_outcome_name    as dribble_outcome_name,
  ev.dribble_overrun         as dribble_overrun,
  ev.dribble_nutmeg          as dribble_nutmeg,
  ev.dribble_no_touch        as dribble_no_touch,

  ------------------------------------------------------------------
  -- 9. BALL RECEIPT (optionnel)
  ------------------------------------------------------------------
  ev.ball_receipt_outcome_id   as ball_receipt_outcome_id,
  ev.ball_receipt_outcome_name as ball_receipt_outcome_name,

  ------------------------------------------------------------------
  -- 10. SHOT (detail complet)
  ------------------------------------------------------------------
  ev.shot_body_part_id       as shot_body_part_id,
  ev.shot_body_part_name     as shot_body_part_name,
  ev.shot_statsbomb_xg       as shot_statsbomb_xg,
  ev.shot_outcome_id         as shot_outcome_id,
  ev.shot_outcome_name       as shot_outcome_name,
  -- flag calculé : TRUE si shot_outcome_name = 'Goal'
  (ev.shot_outcome_name = 'Goal')     as shot_is_goal,
  ev.shot_end_location_x     as shot_end_location_x,
  ev.shot_end_location_y     as shot_end_location_y,
  ev.shot_end_location_z     as shot_end_location_z,
  ev.shot_key_pass_id        as shot_key_pass_id,
  ev.shot_aerial_won         as shot_aerial_won,
  ev.shot_follows_dribble    as shot_follows_dribble,
  ev.shot_first_time         as shot_first_time,
  ev.shot_open_goal          as shot_open_goal,
  ev.shot_deflected          as shot_deflected,
  ev.shot_technique_id       as shot_technique_id,
  ev.shot_technique_name     as shot_technique_name,
  ev.shot_stats_frame        as shot_stats_frame,

  ------------------------------------------------------------------
  -- 11. PRESSURE / 50-50 / BLOCK / CLEARANCE / INTERCEPTION etc.
  ------------------------------------------------------------------
  ev.pressure_counterpress     as pressure_counterpress,

  ev.duel_5050_outcome_id      as duel_5050_outcome_id,
  ev.duel_5050_outcome_name    as duel_5050_outcome_name,
  ev.duel_5050_counterpress    as duel_5050_counterpress,

  ev.block_deflection          as block_deflection,
  ev.block_offensive           as block_offensive,
  ev.block_save_block          as block_save_block,
  ev.block_counterpress        as block_counterpress,

  ev.clearance_aerial_won      as clearance_aerial_won,
  ev.clearance_body_part_id    as clearance_body_part_id,
  ev.clearance_body_part_name  as clearance_body_part_name,

  ev.interception_outcome_id   as interception_outcome_id,
  ev.interception_outcome_name as interception_outcome_name,
  ev.interception_counterpress as interception_counterpress,

  ev.dribbled_past_counterpress as dribbled_past_counterpress,

  ev.duel_counterpress         as duel_counterpress,
  ev.duel_type_id              as duel_type_id,
  ev.duel_type_name            as duel_type_name,
  ev.duel_outcome_id           as duel_outcome_id,
  ev.duel_outcome_name         as duel_outcome_name,

  ev.foul_committed_counterpress as foul_committed_counterpress,
  ev.foul_committed_offensive   as foul_committed_offensive,
  ev.foul_committed_type_id     as foul_committed_type_id,
  ev.foul_committed_type_name   as foul_committed_type_name,
  ev.foul_committed_advantage   as foul_committed_advantage,
  ev.foul_committed_penalty     as foul_committed_penalty,
  ev.foul_committed_card_id     as foul_committed_card_id,
  ev.foul_committed_card_name   as foul_committed_card_name,

  ev.foul_won_defensive         as foul_won_defensive,
  ev.foul_won_advantage         as foul_won_advantage,
  ev.foul_won_penalty           as foul_won_penalty,

  ev.goalkeeper_position_id     as goalkeeper_position_id,
  ev.goalkeeper_position_name   as goalkeeper_position_name,
  ev.goalkeeper_technique_id    as goalkeeper_technique_id,
  ev.goalkeeper_technique_name  as goalkeeper_technique_name,
  ev.goalkeeper_body_part_id    as goalkeeper_body_part_id,
  ev.goalkeeper_body_part_name  as goalkeeper_body_part_name,
  ev.goalkeeper_type_id         as goalkeeper_type_id,
  ev.goalkeeper_type_name       as goalkeeper_type_name,
  ev.goalkeeper_outcome_id      as goalkeeper_outcome_id,
  ev.goalkeeper_outcome_name    as goalkeeper_outcome_name,

  ev.miscontrol_aerial_won      as miscontrol_aerial_won,

  ev.ball_recovery_offensive    as ball_recovery_offensive,
  ev.ball_recovery_failure      as ball_recovery_failure,

  ev.substitution_replacement_id   as substitution_replacement_id,
  ev.substitution_replacement_name as substitution_replacement_name,
  ev.substitution_outcome_id       as substitution_outcome_id,
  ev.substitution_outcome_name     as substitution_outcome_name,

  ev.player_off_permanent       as player_off_permanent,

  ev.bad_behaviour_card_id      as bad_behaviour_card_id,
  ev.bad_behaviour_card_name    as bad_behaviour_card_name

from {{ source('raw', 'events') }} as ev
